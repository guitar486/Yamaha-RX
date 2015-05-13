#! /usr/bin/python2.6
# -*- coding: utf-8 -*-
####################################################################################################

import indigo
import yamaha
import Queue

####################################################################################################
# Plugin
####################################################################################################
class Plugin(indigo.PluginBase):

	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

		# Receiver device placeholder
		self.receiver = None
		self.q = Queue.Queue()


	def __del__(self):
		indigo.PluginBase.__del__(self)

	def startup(self):
		indigo.server.log(u"Yamaha RX plugin started")

	####################################################################################################
	# Actions here execute every time communication is enabled to a device
	####################################################################################################
	def deviceStartComm(self, device):

		# Get copy of device and its ID
		dev = device
		devId = device.id

		# Get IP address from device settings and turn it into RXV control url
		ip = dev.pluginProps.get('receiverIP', '')
		ctrl_url = 'http://' + dev.pluginProps.get("receiverIP", "") + ':80/YamahaRemoteControl/ctrl'

		# Create receiver object
		self.createNewReceiverDevice(dev, devId, ctrl_url)

	####################################################################################################
	# Create RXV Receiver Object and assign it to Plugin self.device
	####################################################################################################
	def createNewReceiverDevice(self, dev, devId, ctrl_url):
		self.receiver = yamaha.RXV(dev, devId, ctrl_url)
		indigo.server.log('Yamaha Receiver created with control url: ' + str(self.receiver.ctrl_url))

	####################################################################################################
	# We call this every time actions are executed and call the RXV receiver object
	####################################################################################################
	def actionHandler(self, pluginAction):

		receiver = self.receiver
		action = pluginAction.pluginTypeId

		# Add this item to the queue to make sure we don't poll the device while executing an action
		self.q.put(action)


		if action == 'volume_up':
			receiver.volume = receiver.volume + 1
		elif action == 'volume_down':
			receiver.volume = receiver.volume - 1
		elif action == 'volume_mute':
			if pluginAction.props['mute_action'] == 'mute_on':
				receiver.mute_on()
			if pluginAction.props['mute_action'] == 'mute_off':
				receiver.mute_off()
			if pluginAction.props['mute_action'] == 'mute_toggle':
				receiver.mute_toggle()
		elif action == 'power_toggle':
			receiver.on = not receiver.on
		elif action == 'set_input':
			receiver.input = pluginAction.props['input']
		elif action == 'sound_program_2ch':
			receiver.sound_program_2ch()

		# Empty the queue, allowing polling to resume
		self.q.get()

	# Returns list of available inputs for selection in action menu
	def get_inputs(self, pluginAction, UiValuesDict, pluginTypeId, devId):
		return self.receiver.inputs().keys()

	####################################################################################################
	# FUTURE -- Figure out how to get list of available Sound Program Modes
	####################################################################################################

	####################################################################################################
	# Infinite loop to poll the receiver and update device states
	####################################################################################################
	def runConcurrentThread(self):
		try:
			while True:

				if self.receiver != None:

					if self.q.empty():

						# Get receiver "basic status"
						status = self.receiver.basic_status

						# On state
						if status[0] == 'On':
						# if self.receiver.on:
							self.receiver.device.updateStateOnServer('power', value='on')
						else:
							self.receiver.device.updateStateOnServer('power', value='standby')

						# Current Volume state
						self.receiver.device.updateStateOnServer('volume', value=status[1])

						# Mute state
						if status[2] == 'Off':
						# if self.receiver.mute == 'Off':
							self.receiver.device.updateStateOnServer('muted', value='false')
						else:
							self.receiver.device.updateStateOnServer('muted', value='true')

						# Current Input state
						self.receiver.device.updateStateOnServer('input', status[3])

				# Time between polling
				self.sleep(1)

		except self.StopThread:
			pass

	def stopConcurrentThread(self):
	    self.stopThread = True
