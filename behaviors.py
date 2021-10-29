import sys
import qi
import time
import select
import signal
import threading
import json
import random
import math
import numpy as np
from PIL import Image
from socket import socket, AF_INET, SOCK_STREAM


class Behaviors:

	def __init__(self):
		self.conn_lock = threading.Lock()
		self.session = qi.Session()
		self.session.connect("tcp://{}:9559".format(sys.argv[1]))
		self.s = None
		self.conn = None
		self.tts_service = self.session.service("ALTextToSpeech")
		self.animated_tts_service = self.session.service("ALAnimatedSpeech")
		self.motion_service = self.session.service("ALMotion")
		self.posture_service = self.session.service("ALRobotPosture")
		self.led_service = self.session.service("ALLeds")
		self.al_service = self.session.service("ALAutonomousLife")

		self.animation_dict = {
			"Thinking": ["BodyTalk/Thinking/Remember_4", "BodyTalk/Thinking/ThinkingLoop_1", "Thinking/ThinkingLoop_2"],
			"Angry": ["Emotions/Negative/Angry_1", "Emotions/Negative/Angry_4"],
			"Sad": ["Emotions/Negative/Bored_1", "Emotions/Negative/Disapointed_1", "Emotions/Negative/Exhausted_1", "Emotions/Negative/Sad_1"],
			"Fearful": ["Emotions/Negative/Fearful_1", "Reactions/TouchHead_3"],
			"Laughing": ["Emotions/Positive/Amused_1", "Emotions/Positive/Laugh_2", "Emotions/Positive/Laugh_3"],
			"Happy": ["Emotions/Positive/Happy_4"],
			"Bowing": ["Gestures/BowShort_1", "Gestures/BowShort_2", "Gestures/BowShort_3"],
			"Waving": ["Gestures/Hey_2"],
			"Showing Tablet": ["Gestures/ShowTablet_1", "Gestures/ShowTablet_2", "Gestures/ShowTablet_3"]
		}

		# robot state
		self.muted = True
		self.breathing = False
		self.head_pitch = "PitchStraight"
		self.head_yaw = "YawStraight"
		self.resting = False
		self.moving = False
		self.locked = False
		if self.al_service.getState() != "disabled":
			self.motion_service.rest()
			self.al_service.setState("disabled")
			self.motion_service.wakeUp()
		if self.motion_service.getStiffnesses('Head')[0] == 0:
			self.motion_service.wakeUp()
		self.motion_service.setBreathEnabled('Body', self.breathing)
		self.set_global_volume(0)
		
		self.motion_service.setStiffnesses('Head', .4)
		self.motion_service.setStiffnesses('LArm', .4)
		self.motion_service.setStiffnesses('RArm', .4)
		self.motion_service.setStiffnesses('Leg', .4)

		# locks
		self.behavior_lock = threading.Lock()
		self.locked_lock = threading.Lock()

		# latency
		self.msg_timestamp = None

		# display the image!
		im = Image.open("img/AWF.png")
		im.show()

	def signal_handler(self, sig, frame):
		self.s.close()
		self.stop_and_lock()
		print("exiting")
		sys.exit(0)

	def connection_manager(self):
		'''
		Intermittently check whether a connection is open
		'''
		while True:
			time.sleep(2.0)
			if self.conn_lock.acquire(False):
				print("Attempting connection...")
				self.conn_lock.release()
				self.s = socket(AF_INET, SOCK_STREAM)
				self.conn = None
				thread = threading.Thread(target=self.connect_and_listen_wrapper)
				thread.daemon = True		# Daemonize thread
				thread.start()
			else:
				pass

	def connect_and_listen_wrapper(self):
		"""Wrap everything in a try-except to ensure that any errors cause the robot to stop."""
		try:
			self.connect_and_listen()
		except:
			print("Error encountered. Bringing robot to full stop.")
		self.stop_and_lock()
		self.s.close()
		self.conn = None
		print("Connection closed.")
		self.conn_lock.release()

	def connect_and_listen(self):
		self.conn_lock.acquire()
		while True:
			try:
				self.s.bind((sys.argv[1], 8888))
				self.s.listen(1)
				self.conn, addr = self.s.accept()  # accepts the connection
				print("Connected to: ", addr)  # prints the connection
				break
			except:
				print("Unable to connect to client. Retrying...")
				time.sleep(1)

		# Key:
		# 
		# LOCOMOTION:
		# velocity = forward, backward
		# twist = rotation
		#
		# POSTURE:
		# a = standing
		# b = resting
		# x = welcoming
		# y = hands on hips
		#
		# META BEHAVIORS:
		# lb = what next?
		# rb = thank you
		# center = motion aloha
		# info = EMERGENCY STOP + LOCK
		# start = unlock
		#
		# HEAD
		# up = move up
		# down = move down
		# left = move left
		# right = move right
		#
		# OPTIONS
		# left joy button = breath on/off
		# right joy button = mute on/off
		cutoff = b''
		while True:
			try:
				read_s, _, _ = select.select([self.conn], [], [])
				msg_timestamp = time.time()
				if self.msg_timestamp is not None and msg_timestamp - self.msg_timestamp > 2.0:
					print("High latency detected.")
					self.msg_timestamp = None
					break
				self.msg_timestamp = msg_timestamp
				data_bytes = cutoff + read_s[0].recv(2048)  # receiving data
				cutoff = b''
				all_str = [d for d in data_bytes.decode().split("\n") if len(d) > 0]
				data_str = [d for d in all_str if d[0] == "{" and d[-1] == "}"]
				if len(all_str) > 0 and "}" not in all_str[-1] and "{" in all_str[-1]:
					cutoff = all_str[-1]
				data = json.loads(data_str[-1])
			except:
				print("Error encountered when receiving data.")
				break

			thread = threading.Thread(target=self.behavior_decider, args=(data,))
			thread.daemon = True		# Daemonize thread
			thread.start()	

	def behavior_decider(self, ev):
		# return if locked
		if self.is_locked():
			if ev["start"]:
				self.unlock()
			return

		# ignore behavior commands if resting
		if self.resting:
			if self.behavior_lock.acquire(False):  # non-blocking
				# the only command that we can recognize is "standing"
				if ev["a"]:
					self.motion_service.wakeUp()
					self.resting = False
				elif sum(list(ev.values())) > 0:
					print("Can not execute non-wakeUp behavior when robot is resting.")
				self.behavior_lock.release()
			elif sum(list(ev.values())) > 0:
				print("Can not execute new behavior as another behavior is still executing!")

		else:
			# ALWAYS update the velocity, twist, and emergency stop/lock/unlock
			forward = ev["velocity"] * 0.4
			twist = ev["twist"] * 0.6
			print(forward)
			stop_and_lock = ev["info"]
			self.locomote(forward, twist)
			if stop_and_lock:
				self.stop_and_lock()
				return

			if self.behavior_lock.acquire(False):  # non-blocking
				# ALWAYS respond to option toggling requests
				# options
				if ev["left joy button"]:
					self.toggle_breath()
				if ev["right joy button"]:
					self.toggle_mute()

				# ONLY one behavior can run at a time from here on
				# meta behaviors
				if ev["lb"]:
					self.say_whats_next()
				elif ev["rb"]:
					self.thank_you()
				elif ev["center"]:
					self.motion_aloha()

				# posture
				elif ev["a"]:
					self.posture({"position": "Standing", "duration": 4.0})
				elif ev["b"]:
					self.resting = True
					# self.posture({"position": "Resting", "duration": 4.0})
					self.motion_service.rest()
				elif ev["x"]:
					self.posture({"position": "Welcoming", "duration": 4.0})
				elif ev["y"]:
					self.posture({"position": "Hands on hips", "duration": 4.0})

				# head
				elif ev["up"]:
					self.head({"position": "up", "duration": 2.0})
				elif ev["down"]:
					self.head({"position": "down", "duration": 2.0})
				elif ev["left"]:
					self.head({"position": "left", "duration": 2.0})
				elif ev["right"]:
					self.head({"position": "right", "duration": 2.0})

				self.behavior_lock.release()
			elif sum(list(ev.values())) > 0:
				print("Can not execute new behavior as another behavior is still executing!")

	###########################
	# Behavior Implementations
	###########################
	def stop_and_lock(self):
		self.locked_lock.acquire()
		# stop everything immediately!
		self.locomote(0, 0)
		self.tts_service.stopAll()
		names = ["HeadPitch", "HeadYaw",
				 "LWristYaw", "LShoulderRoll", "LShoulderPitch", "LElbowRoll", "LElbowYaw", "LHand",
				 "RWristYaw", "RShoulderRoll", "RShoulderPitch", "RElbowRoll", "RElbowYaw", "RHand",
				 "HipPitch", "HipRoll", "KneePitch"]
		curr_angles = self.motion_service.getAngles(names, True)
		self.motion_service.setAngles(names, curr_angles, 0.1)
		self.set_stiffness(0.6, "Body")
		self.locked = True
		print("Emergency stop and lock. You must unlock the robot to continue using it.")
		self.locked_lock.release()

	def unlock(self):
		print("unlocking robot...")
		self.locked_lock.acquire()
		self.locked = False
		self.locked_lock.release()
		print("Robot unlocked.")

	def is_locked(self):
		locked = False
		self.locked_lock.acquire()
		if self.locked:
			locked = True
		self.locked_lock.release()
		return locked

	def say_whats_next(self):
		self.posture({"position": "Welcoming", "duration": 2.5})
		self.say({"speech": "What \\emph=1\\\\vct=130\\next?", "volume": 200, "pitch": 100, "speed": 75, "animation": "None"})
		self.posture({"position": "Standing", "duration": 2.5})

	def thank_you(self):
		self.say({"speech": "Thank you for seeing the potential in robots like me.", "volume": 200, "pitch": 100, "speed": 80, "animation": "Bowing"})

	def motion_aloha(self):
		thread = threading.Thread(target=self.head_animation)
		thread.daemon = True		# Daemonize thread
		thread.start()
		self.wave_animation()

	def toggle_breath(self):
		if self.breathing:
			self.breathing = False
			print("breathing off")
		else:
			self.breathing = True
			print("breathing on")
		self.motion_service.setBreathEnabled('Body', self.breathing)

	def toggle_mute(self):
		if self.muted:
			self.muted = False
			self.set_global_volume(1.0)
			print("unmuted")
		else:
			self.muted = True
			self.set_global_volume(0)
			print("muted")

	def arm(self, params):
		'''
		"Left Extended": 
		"Right Extended":
		"Left Retracted":
		"Right Retracted":
		"Left Open":
		"Right Open",:
		"Left Grasping":
		"Right Grasping:
		'''
		category = params["position"]
		duration = params["duration"]
		print("Robot moving arm to {} at duration {}".format(category, duration))
		if category == "Left Extended":
			names = ["LWristYaw", "LShoulderRoll", "LShoulderPitch", "LElbowRoll", "LElbowYaw"]
			angles = [math.radians(-81.2), math.radians(11.5), math.radians(46.9), math.radians(-40.9), math.radians(-98.0)]
		if category == "Right Extended":
			names = ["RWristYaw", "RShoulderRoll", "RShoulderPitch", "RElbowRoll", "RElbowYaw"]
			angles = [math.radians(81.2), math.radians(-11.5), math.radians(46.9), math.radians(40.9), math.radians(98.0)]
		if category == "Left Retracted":
			names = ["LWristYaw", "LShoulderRoll", "LShoulderPitch", "LElbowRoll", "LElbowYaw"]
			angles = [math.radians(1.9), math.radians(6.0), math.radians(101.2), math.radians(-6.5), math.radians(-98.0)]
		if category == "Right Retracted":
			names = ["RWristYaw", "RShoulderRoll", "RShoulderPitch", "RElbowRoll", "RElbowYaw"]
			angles = [math.radians(-1.3), math.radians(-6.0), math.radians(100.0), math.radians(5.9), math.radians(98.0)]
		if category == "Left Open":
			names = ["LHand"]
			angles = [0.98]
		if category == "Right Open":
			names = ["RHand"]
			angles = [0.98]
		if category == "Left Grasping":
			names = ["LHand"]
			angles = [.26]
		if category == "Right Grasping":
			names = ["RHand"]
			angles = [.26]
		time_ip, angles_ip = self.ip(names, angles, duration)
		self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
		print("Done moving arm to {} at speed {}".format(category, duration))

	def head(self, params):
		category = params["position"]
		duration = params["duration"]
		if category == "up":
			if self.head_pitch == "Up":
				pass
			elif self.head_pitch == "PitchStraight":
				self.head_pitch = "Up"
			elif self.head_pitch == "Down":
				self.head_pitch = "PitchStraight"
			category = self.head_pitch
		elif category == "down":
			if self.head_pitch == "Up":
				self.head_pitch = "PitchStraight"
			elif self.head_pitch == "PitchStraight":
				self.head_pitch = "Down"
			elif self.head_pitch == "Down":
				pass
			category = self.head_pitch
		elif category == "left":
			if self.head_yaw == "Right":
				self.head_yaw = "YawStraight"
			elif self.head_yaw == "YawStraight":
				self.head_yaw = "Left"
			elif self.head_yaw == "Left":
				pass
			category = self.head_yaw
		elif category == "right":
			if self.head_yaw == "Right":
				pass
			elif self.head_yaw == "YawStraight":
				self.head_yaw = "Right"
			elif self.head_yaw == "Left":
				self.head_yaw = "YawStraight"
			category = self.head_yaw
		if category == "YawStraight":
			names = ["HeadYaw"]
			angles = [math.radians(1.1)]
		if category == "PitchStraight":
			names = ["HeadPitch"]
			angles = [math.radians(-21.9)]
		if category == "Up":
			names = ["HeadPitch"]
			angles = [math.radians(-40.5)]
		if category == "Down":
			names = ["HeadPitch"]
			angles = [math.radians(25.5)]
		if category == "Left":
			names = ["HeadYaw"]
			angles = [math.radians(49.0)]
		if category == "Right":
			names = ["HeadYaw"]
			angles = [math.radians(-49.0)]
		print("Robot moving head to {} at duration {}".format(category, duration))
		time_ip, angles_ip = self.ip(names, angles, duration)
		self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
		print("Done moving head to {} at speed {}".format(category, duration))

	def posture(self, params):
		category = params["position"]
		duration = params["duration"]
		names = ["HeadPitch", "HeadYaw",
				 "LWristYaw", "LShoulderRoll", "LShoulderPitch", "LElbowRoll", "LElbowYaw", "LHand",
				 "RWristYaw", "RShoulderRoll", "RShoulderPitch", "RElbowRoll", "RElbowYaw", "RHand",
				 "HipPitch", "HipRoll", "KneePitch"]
		if category == "Standing":
			angles = [math.radians(-11.1), math.radians(0.0),
					  math.radians(1.9), math.radians(6.0), math.radians(101.2), math.radians(-6.5), math.radians(-98.0), 0.60,
					  math.radians(-1.3), math.radians(-6.0), math.radians(100.0), math.radians(5.9), math.radians(98.0), 0.60,
					  math.radians(-2.0), math.radians(0.0), math.radians(0.6)]
		elif category == "Resting":
			angles = [math.radians(25.5), math.radians(0.0),
					  math.radians(-46.2), math.radians(3.4), math.radians(65.5), math.radians(-0.6), math.radians(-27.9), 0.60,
					  math.radians(46.2), math.radians(-3.6), math.radians(65.2), math.radians(0.5), math.radians(27.8), 0.60,
					  math.radians(-59.5), math.radians(0.0), math.radians(28.9)]
		elif category == "Welcoming": 
			angles = [math.radians(-11.1), math.radians(0.0),
					  math.radians(1.9), math.radians(43.6), math.radians(71.3), math.radians(-39.8), math.radians(-119.4), 0.74,
					  math.radians(22.7), math.radians(-24.7), math.radians(59.9), math.radians(41.8), math.radians(119.1), 0.70,
					  math.radians(-2.0), math.radians(0.0), math.radians(0.6)]
		elif category == "Hands on hips":
			angles = [math.radians(-11.1), math.radians(0.0),
					  math.radians(-103.5), math.radians(48.5), math.radians(85.2), math.radians(-85.7), math.radians(-11.0), 0.13,
					  math.radians(104.1), math.radians(-48.7), math.radians(74.6), math.radians(89.5), math.radians(-7.1), 0.02,
					  math.radians(-2.0), math.radians(0.0), math.radians(0.6)]
		print("{} at duration {}".format(category, duration))
		self.set_stiffness(0.9, "Body")
		time_ip, angles_ip = self.ip(names, angles, duration)
		self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
		self.set_stiffness(0.6, "Body")
		print("Done {} at duration {}".format(category, duration))

	def mood(self, params):
		colors = {
			"Red": 0x00FF0000,
			"Orange": 0x00FF7300,
			"Yellow": 0x00FFFB00,
			"Green": 0x000DFF00,
			"Blue": 0x000D00FF,
			"Violet": 0x009D00FF,
			"Neutral": 0x00FFFFFF
		}
		category = params["color"]
		code = colors[category]
		fade_duration = 0.2
		self.led_service.fadeRGB("FaceLeds", code, fade_duration)
		self.led_service.fadeRGB("ChestLeds", code, fade_duration)
	
	def get_animation(self, param):
		try:
			anim_list = self.animation_dict[param]
			return "^start(animations/Stand/" + anim_list[random.randint(0, len(anim_list) - 1)] + ")"
		except:
			return ""

	def set_global_volume(self, value):
		self.tts_service.setVolume(value)

	def set_global_pitch(self, value):
		self.tts_service.setParameter("pitchShift", value)

	def say(self, params):
		speech = params["speech"]
		volume = params["volume"]
		pitch = params["pitch"]
		speed = params["speed"]
		animation = params["animation"]
		tts = self.animated_tts_service
		animation_string = ""

		if animation == "None":
			tts = self.tts_service
		elif animation != "Default":
			animation_string = self.get_animation(animation)
		print(animation_string)
		
		print("Robot saying {}".format(speech))
		tts.say("{}\\vol={}\\\\vct={}\\\\rspd={}\\{}".format(animation_string, volume, pitch, speed, speech))
		print("Robot done saying")

	def locomote(self, forward, yaw):
		if self.moving:
			self.motion_service.move(forward, 0, yaw)
		if abs(forward) > 0 or abs(yaw) > 0:
			self.moving = True
			print("moving - {}, {}".format(forward, yaw))
		else:
			self.moving = False

	def head_animation(self):
		# -21.5 <= pitch <= 8.2
		# -41.7 <= yaw <= 41.7
		# 0.2 <= time <= 0.8
		print("Beginning head animation.")
		start_time = time.time()
		time_elapsed = 0.0
		while time_elapsed < 12.0:
			names = ["HeadPitch", "HeadYaw"]
			angles = [math.radians(random.uniform(-21.5, 8.2)), math.radians(random.uniform(-41.7, 41.7))]
			time_ip, angles_ip = self.ip(names, angles, random.uniform(1.0, 2.8))
			self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
			time_elapsed = (time.time() - start_time)
		print("Finished head animation.")

	def wave_animation(self):
		try:
			print("Setting up wave behavior...")
			start_time = time.time()
			time_elapsed = 0.0
			names = ["LWristYaw", "LShoulderRoll", "LShoulderPitch", "LElbowRoll", "LElbowYaw", "LHand"]
			angles = [math.radians(62.1), math.radians(30.9), math.radians(-22.9), math.radians(-52.4), math.radians(-73.1), 0.98]
			time_ip, angles_ip = self.ip(names, angles, 4.0)
			self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
			print("Wave: done moving arm to initial pos...")

			while time_elapsed < 12.0:
				names = ["LWristYaw"]
				angles = [math.radians(66.5)]
				time_ip, angles_ip = self.ip(names, angles, 2.0)
				self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
				angles[0] = math.radians(-16.9)
				time_ip, angles_ip = self.ip(names, angles, 2.0)
				self.motion_service.angleInterpolation(names, angles_ip, time_ip, True)
				time_elapsed = (time.time() - start_time)
			print("Wave finished.")
		except:
			print("Wave animation failed.")

	def set_stiffness(self, val, names):
		stiffnessLists = val
		timeLists = 1.0
		self.motion_service.stiffnessInterpolation(names, stiffnessLists, timeLists)

	def ip(self, joints, target_angles, seconds):
		'''
		Joints -- list of joints to interpolate
		target_angles - list of target angles, NOT CONVERTED to radians
		'''
		time_dividor = 100
		curr_angles = self.motion_service.getAngles(joints, True)
		angle_multipliers = np.linspace(-6, 6, time_dividor)
		angle_multipliers = 1 / (1 + np.exp(-angle_multipliers))
		time_fragment = seconds / time_dividor
		time_fractions = [i * time_fragment for i in range(1, time_dividor)]
		time_fractions.append(seconds)
		angles_interpolated = []
		for i in range(len(target_angles)):
			start = curr_angles[i]
			end = target_angles[i]
			interp = [start + (end - start) * mult.item() for mult in angle_multipliers]
			angles_interpolated.append(interp)
		times = [time_fractions for i in target_angles]
		return times, angles_interpolated


if __name__ == "__main__":
	b = Behaviors()
	signal.signal(signal.SIGINT, b.signal_handler)
	b.connection_manager()
