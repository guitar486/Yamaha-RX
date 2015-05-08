####################################################################################################
# Copyright (c) 2013, Joanna Tustanowska & Wojciech Bederski
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that # the following conditions are met:
#
#     - Redistributions of source code must retain the above copyright notice, this list of conditions and the
#       following disclaimer.
#     - Redistributions in binary form must reproduce the above copyright notice, this list of conditions and
#       the following disclaimer in the documentation and/or other materials provided with the distribution.
#     - Names of contributors may not be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
####################################################################################################

import re
import time
import requests
import warnings
import xml.etree.ElementTree as ET
from math import floor
from collections import namedtuple
from multiprocessing import Process

import plugin
import indigo


BasicStatus = namedtuple("BasicStatus", "on volume mute input")
MenuStatus = namedtuple("MenuStatus", "ready layer name current_line max_line current_list")

GetParam = 'GetParam'
YamahaCommand = '<YAMAHA_AV cmd="{command}">{payload}</YAMAHA_AV>'
MainZone = '<Main_Zone>{request_text}</Main_Zone>'
Zone2 = '<Zone_2>{request_text}</Zone_2>'
BasicStatusGet = '<Basic_Status>GetParam</Basic_Status>'
PowerControl = '<Power_Control><Power>{state}</Power></Power_Control>'
PowerControlSleep = '<Power_Control><Sleep>{sleep_value}</Sleep></Power_Control>'
Input = '<Input><Input_Sel>{input_name}</Input_Sel></Input>'
InputSelItem = '<Input><Input_Sel_Item>{input_name}</Input_Sel_Item></Input>'
ConfigGet = '<{src_name}><Config>GetParam</Config></{src_name}>'
ListGet = '<{src_name}><List_Info>GetParam</List_Info></{src_name}>'
ListControlJumpLine = '<{src_name}><List_Control><Jump_Line>{lineno}</Jump_Line>' \
                      '</List_Control></{src_name}>'
ListControlCursor = '<{src_name}><List_Control><Cursor>{action}</Cursor></List_Control></{src_name}>'
VolumeLevel = '<Volume><Lvl>{value}</Lvl></Volume>'
VolumeLevelValue = '<Val>{val}</Val><Exp>{exp}</Exp><Unit>{unit}</Unit>'
SelectNetRadioLine = '<NET_RADIO><List_Control><Direct_Sel>Line_{lineno}'\
                     '</Direct_Sel></List_Control></NET_RADIO>'

ProgramMode = '<Surround><Program_Sel><Current><Sound_Program>{mode}</Sound_Program></Current></Program_Sel></Surround>'
Mute = '<Volume><Mute>{state}</Mute></Volume>'


# model_name = 'RX-V675'

class RXV(object):

    def __init__(self, device, deviceId, ctrl_url='', model_name="Unknown"):
        self.deviceId = deviceId
        self.device = device
        self.ctrl_url = ctrl_url
        self.model_name = model_name
        self._inputs_cache = None

    def _request(self, command, request_text, zone=1):
        if zone == 1:
            payload = MainZone.format(request_text=request_text)
        elif zone == 2:
            payload = Zone2.format(request_text=request_text)

        request_text = YamahaCommand.format(command=command, payload=payload)
        try:
            res = requests.post(
                self.ctrl_url,
                data=request_text,
                headers={"Content-Type": "text/xml"},
                timeout=4
            )
        except requests.exceptions.ConnectTimeout:
            indigo.server.log('Timed out trying to reack ' + str(self.ctrl_url))
            return

        response = ET.XML(res.content)
        return response

    @property
    def basic_status(self):
        response = self._request('GET', BasicStatusGet)
        on = response.find("Main_Zone/Basic_Status/Power_Control/Power").text
        inp = response.find("Main_Zone/Basic_Status/Input/Input_Sel").text
        mute = response.find("Main_Zone/Basic_Status/Volume/Mute").text
        volume = response.find("Main_Zone/Basic_Status/Volume/Lvl/Val").text
        volume = int(volume) / 10.0

        status = BasicStatus(on, volume, mute, inp)
        return status

    @property
    def on(self):
        request_text = PowerControl.format(state=GetParam)
        response = self._request('GET', request_text)
        power = response.find("Main_Zone/Power_Control/Power").text
        assert power in ["On", "Standby"]
        return power == "On"

    @on.setter
    def on(self, state):
        assert state in [True, False]
        new_state = "On" if state else "Standby"
        request_text = PowerControl.format(state=new_state)
        response = self._request('PUT', request_text)
        return response

    def off(self):
        return self.on(False)

    @property
    def input(self):
        request_text = Input.format(input_name=GetParam)
        response = self._request('GET', request_text)
        return response.find("Main_Zone/Input/Input_Sel").text

    @input.setter
    def input(self, input_name):
        assert input_name in self.inputs()
        request_text = Input.format(input_name=input_name)
        self._request('PUT', request_text)

    def inputs(self):
        if not self._inputs_cache:
            request_text = InputSelItem.format(input_name=GetParam)
            res = self._request('GET', request_text)
            self._inputs_cache = dict(zip((elt.text for elt in res.getiterator('Param')), (elt.text for elt in res.getiterator("Src_Name"))))
        return self._inputs_cache

    @property
    def volume(self):
        request_text = VolumeLevel.format(value=GetParam)
        response = self._request('GET', request_text)
        vol = response.find('Main_Zone/Volume/Lvl/Val').text
        return float(vol) / 10.0

    @volume.setter
    def volume(self, value):
        value = str(int(value * 10))
        exp = 1
        unit = 'dB'
        volume_val = VolumeLevelValue.format(val=value, exp=exp, unit=unit)
        request_text = VolumeLevel.format(value=volume_val)
        self._request('PUT', request_text)

    @property
    def mute(self):
        request_text = Mute.format(state=GetParam)
        response = self._request('GET', request_text)
        return response.find('Main_Zone/Volume/Mute').text

    def mute_on(self):
        request_text = Mute.format(state='On')
        self._request('PUT', request_text)

    def mute_off(self):
        request_text = Mute.format(state='Off')
        self._request('PUT', request_text)

    def mute_toggle(self):
        state = self.mute
        new_state = 'Off' if state == 'On' else 'On'
        request_text = Mute.format(state=new_state)
        self._request('PUT', request_text)

    def volume_fade(self, final_vol, sleep=0.5):
        start_vol = int(floor(self.volume))
        step = 1 if final_vol > start_vol else -1
        final_vol += step  # to make sure, we don't stop one dB before

        for val in range(start_vol, final_vol, step):
            self.volume = val
            time.sleep(sleep)

    @property
    def sleep(self):
        request_text = PowerControlSleep.format(state=GetParam)
        response = self._request('GET', request_text)
        sleep = response.find("Main_Zone/Power_Control/Sleep").text
        return sleep

    @sleep.setter
    def sleep(self, value):
        request_text = PowerControlSleep.format(sleep_value=value)
        self._request('PUT', request_text)

    def sound_program_2ch(self):
        request_text = ProgramMode.format(mode='2ch Stereo')
        self._request('PUT', request_text)
