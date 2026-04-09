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

WS_ADDRESS = "ws://localhost"
WS_PORT = 5000
# API_FILE_PATH = os.path.join(project.folder, "..", "Scripts", "td_realtime_api.py")  # type: ignore


def _create_op(op_type, name, x=0, y=0):
    existing = parent.op(name)
    if existing:
        existing.destroy()
    node = parent.create(op_type, name)
    node.nodeX = x
    node.nodeY = y
    return node


def _get_op(name):
    return parent.op(name)


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
	print(message)
	if message == "ping":
		dat.sendText("pong")
		return
	data = json.loads(message)
	table = op("incoming_data")
	# write key and values into a table
	for key, val in data.items():
		if table.findCell(key):
			table.replaceRow(key, [key, val])
		else:
			table.appendRow([key, val])
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
# --- EX: SEND DATA TO TD FROM WEB SERVER ---
incoming_data = _create_op(td.tableDAT, "incoming_data", 0, -300)
incoming_data.viewer = True
incoming_data.clear()

dat_to_chop = _create_op(td.dattoCHOP, "datto1", 200, -300)
dat_to_chop.viewer = True
dat_to_chop.par.dat = incoming_data.name
dat_to_chop.par.output = 1  # Output = Channel per Row
dat_to_chop.par.firstrow = 2  # First Row = Values
dat_to_chop.par.firstcolumn = 1  # First Column = Names

# --- EX: SEND DATA FROM TD TO WEB SERVER ---
slider = _create_op(td.sliderCOMP, "slider1", 0, -500)
slider.viewer = True

slider_null = _create_op(td.nullCHOP, "slider1_null", 200, -500)
slider_null.viewer = True
slider_null.inputConnectors[0].connect(slider.outputConnectors[0])

slider_exec = _create_op(td.chopexecuteDAT, "slider1_exec", 400, -500)
slider_exec.viewer = True
slider_exec.par.chop = slider_null.name
slider_exec.par.valuechange = 1  # track when value changes
slider_exec.text = '''
import json

ws = op('websocket')

def onValueChange(channel: Channel, sampleIndex: int, val: float, 
				  prev: float):
	"""
	Called when a channel value changes.
	
	Args:
		channel: The Channel object which has changed
		sampleIndex: The index of the changed sample
		val: The numeric value of the changed sample
		prev: The previous sample value
	"""
	raw_name = channel.owner.name
	op_name = raw_name.replace("_null", "")
	
	data_to_send = {op_name: val}
	json_string = json.dumps(data_to_send)
	ws.sendText(json_string)
	return
'''
