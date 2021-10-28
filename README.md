# Pepper Joystick Demo

## Installation

Any python version that runs pygame should work. Make sure you have an XBox One USB gamepad plugged in and `pygame` installed on your own machine:

```
python -m pip install pygame
```

### Physical Pepper Robot

Boot the robot and take note of its IP address. On your own machine:

```
cd /path/to/PepperJoystickDemo
scp behaviors.py nao@ROBOT_IP
scp AWF.png nao@ROBOT_IP
```

### Virtual Pepper Robot

You must have a licensed copy of Choregraphe. You must also install the C++ Naoqi libraries from Softbank's website.

## Running

### Physical Pepper Robot

In one terminal:

```
ssh nao@ROBOT_IP
python behavior.py ROBOT_IP
```

In another terminal:

```
python main.py ROBOT_IP
```

### Virtual Pepper Robot

In one terminal:

```
cd /path/to/naoqi
./naoqi
```

In a second terminal:

```
python behavior.py localhost
```

In a third terminal:

```
python main.py localhost
```