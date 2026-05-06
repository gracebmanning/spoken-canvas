"""
td_setup.py
===============
Run this as a Text DAT inside TouchDesigner to set up the real-time
WebSocket infrastructure. Right-click the Text DAT → Run Script.
"""

import td  # type: ignore
import os

parent = me.parent()   # type: ignore
project = td.project    # type: ignore

WS_ADDRESS = "ws://localhost/ws"
WS_PORT = 8000

API_FILE = os.path.join(project.folder, "..", "td_api.py")


def _create_op(op_type, name, x=0, y=0, parent_op=parent):
    existing = parent_op.op(name)
    if existing:
        existing.destroy()
    node = parent_op.create(op_type, name)
    node.nodeX = x
    node.nodeY = y
    return node


def _get_op(name, parent_op=parent):
    return parent_op.op(name)


# --- WEB SOCKET SETUP ---
websocketDAT = _create_op(td.websocketDAT, "websocket", 0, 0)
websocketDAT.par.netaddress = WS_ADDRESS
websocketDAT.par.port = WS_PORT
websocketDAT.viewer = True

callbacksDAT = _get_op(websocketDAT.par.callbacks)
callbacksDAT.text = '''
"""
WebSocket DAT Callbacks
me - this DAT
dat - the WebSocket DAT
"""
import json

def onConnect(dat: websocketDAT):
	"""
	Called when a WebSocket connection is established.
	"""
	print("connected")
	return

def onDisconnect(dat: websocketDAT):
	"""
	Called when a WebSocket connection is disconnected.
	"""
	print("disconnected")
	return

def onReceiveText(dat: websocketDAT, rowIndex: int, message: str):
	"""
	Called when a text frame message is received. Only text frame messages 
	will be handled in this function.
	
	Args:
		dat: The DAT that received a message
		rowIndex: The row number the message was placed into
		message: A unicode representation of the text
	"""
	if message == "ping":
		dat.sendText("pong")
		return
	
	data = json.loads(message)
	
	# Only handle messages targeted at TD
	if data.get("target") != "td":
		return
	
	command = data.get("command")
	print(f"TD received command: {command}")
	
	if command == "execute":
		mod(op("td_api")).handle(data)
	elif command == "update_position":
		# Store silently for future use
		table = op("position_data")
		table.clear()
		table.appendRow(["position",   data.get("position", 0)])
		table.appendRow(["totalWords", data.get("totalWords", 0)])
		table.appendRow(["plainText",  data.get("plainText", "")])
	return


def onReceiveBinary(dat: websocketDAT, contents: bytes):
	"""
	Called when a binary frame message is received. Only binary frame 
	messages will be handled in this function.
	
	Args:
		dat: The DAT that received a message
		contents: A byte array of the message contents
	"""
	return

def onReceivePing(dat: websocketDAT, contents: bytes):
	"""
	Called when a ping message is received. Only ping messages will be 
	handled in this function.
	
	Args:
		dat: The DAT that received a message
		contents: A byte array of the message contents
	"""
	dat.sendPong(contents) # send a reply with same message
	return

def onReceivePong(dat: websocketDAT, contents: bytes):
	"""
	Called when a pong message is received. Only pong messages will be 
	handled in this function.
	
	Args:
		dat: The DAT that received a message
		contents: A byte array of the message content
	"""
	return

def onMonitorMessage(dat: websocketDAT, message: str):
	"""
	Called to monitor the websocket status messages.
	
	Args:
		dat: The DAT that received a message
		message: A unicode representation of the message
	"""
	return
'''

# --- TD API ---
td_api = _create_op(td.textDAT, "td_api", 200, 0)
td_api.viewer = True
td_api.par.file = API_FILE
td_api.par.language = 3  # set language to Python
td_api.par.syncfile = 1  # set Sync to File on

# --- POSITION DATA ---
# Silently stores update_position messages for future use
position_data = _create_op(td.tableDAT, "position_data", 0, -300)
position_data.viewer = True
position_data.clear()

# --- INCOMING DATA ---
incoming_data = _create_op(td.tableDAT, "incoming_data", 0, -500)
incoming_data.viewer = True
incoming_data.clear()

dat_to_chop = _create_op(td.dattoCHOP, "datto1", 200, -500)
dat_to_chop.viewer = True
dat_to_chop.par.dat = incoming_data.name
dat_to_chop.par.output = 1  # Output = Channel per Row
dat_to_chop.par.firstrow = 2  # First Row = Values
dat_to_chop.par.firstcolumn = 1  # First Column = Names

# --- SHAPES CONTAINER ---
shapes_container = _create_op(td.baseCOMP, "shapes", 400, -500)
shapes_container.viewer = True

shapes_data_in = _create_op(td.inCHOP, "shapes_data_in", -475, 0, shapes_container)
shapes_data_in.viewer = True
shapes_container.inputConnectors[0].connect(dat_to_chop.outputConnectors[0])

shapes_camera = _create_op(td.cameraCOMP, "camera", 0, 0, shapes_container)
shapes_camera.viewer = True

shapes_light = _create_op(td.lightCOMP, "light", 250, 0, shapes_container)
shapes_light.viewer = True

shapes_composite = _create_op(td.compositeTOP, "shapes_composite", 725, -175, shapes_container)
shapes_composite.viewer = True
shapes_composite.par.operand = 31  # Over operation

shapes_out = _create_op(td.outTOP, "shapes_out", 975, -175, shapes_container)
shapes_out.viewer = True
shapes_out.setInputs([shapes_composite])

shapes_final_out = _create_op(td.outTOP, "shapes_final_out", 600, -500)
shapes_final_out.viewer = True
shapes_final_out.inputConnectors[0].connect(shapes_container.outputConnectors[0])

# --- SEND VISUALS TO OBS VIA NDI ---
ndi_out = _create_op(td.ndioutTOP, "NDI_out", 800, -500)
ndi_out.par.active = 1
ndi_out.par.name = "TouchDesigner"
ndi_out.par.includealpha = 1
ndi_out.inputConnectors[0].connect(shapes_final_out.outputConnectors[0])

# --- CAPTURE MIC AUDIO AND SEND TO SHAPES ---
audio_analysis = _create_op(td.baseCOMP, "audio_analysis", 0, -700)

audio_dev_in = _create_op(td.audiodeviceinCHOP, "audio_dev_in", 0, 0, audio_analysis)
audio_dev_in.viewer = True

audio_analyze = _create_op(td.analyzeCHOP, "analyze1", 200, 0, audio_analysis)
audio_analyze.viewer = True
audio_analyze.par.function = 6  # Function = RMS Power
audio_analyze.setInputs([audio_dev_in])

# Math: From (0, 0.1) and To (0, 1)
audio_math = _create_op(td.mathCHOP, "math1", 400, 0, audio_analysis)
audio_math.viewer = True
audio_math.par.fromrange2 = 0.04
audio_math.setInputs([audio_analyze])

audio_lag = _create_op(td.lagCHOP, "lag1", 600, 0, audio_analysis)
audio_lag.viewer = True
audio_lag.par.lag1 = 0.1
audio_lag.par.lag2 = 0.1
audio_lag.inputConnectors[0].connect(audio_math.outputConnectors[0])

audio_out = _create_op(td.outCHOP, "out1", 800, 0, audio_analysis)
audio_out.setInputs([audio_lag])

# connect to shapes container
sound_data_in = _create_op(td.inCHOP, "sound_data_in", -475, -200, shapes_container)
sound_data_in.viewer = True
shapes_container.inputConnectors[1].connect(audio_analysis.outputConnectors[0])

# # --- EX: SEND DATA TO TD FROM WEB SERVER ---
# incoming_data = _create_op(td.tableDAT, "incoming_data", 0, -300)
# incoming_data.viewer = True
# incoming_data.clear()

# dat_to_chop = _create_op(td.dattoCHOP, "datto1", 200, -300)
# dat_to_chop.viewer = True
# dat_to_chop.par.dat = incoming_data.name
# dat_to_chop.par.output = 1  # Output = Channel per Row
# dat_to_chop.par.firstrow = 2  # First Row = Values
# dat_to_chop.par.firstcolumn = 1  # First Column = Names

# # --- EX: SEND DATA FROM TD TO WEB SERVER ---
# slider = _create_op(td.sliderCOMP, "slider1", 0, -500)
# slider.viewer = True

# slider_null = _create_op(td.nullCHOP, "slider1_null", 200, -500)
# slider_null.viewer = True
# slider_null.inputConnectors[0].connect(slider.outputConnectors[0])

# slider_exec = _create_op(td.chopexecuteDAT, "slider1_exec", 400, -500)
# slider_exec.viewer = True
# slider_exec.par.chop = slider_null.name
# slider_exec.par.valuechange = 1  # track when value changes
# slider_exec.text = '''
# import json

# ws = op('websocket')

# def onValueChange(channel: Channel, sampleIndex: int, val: float,
# 				  prev: float):
# 	"""
# 	Called when a channel value changes.

# 	Args:
# 		channel: The Channel object which has changed
# 		sampleIndex: The index of the changed sample
# 		val: The numeric value of the changed sample
# 		prev: The previous sample value
# 	"""
# 	raw_name = channel.owner.name
# 	op_name = raw_name.replace("_null", "")

# 	data_to_send = {op_name: val}
# 	json_string = json.dumps(data_to_send)
# 	ws.sendText(json_string)
# 	return
# '''
