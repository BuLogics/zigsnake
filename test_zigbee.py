#!/usr/bin/env python
import zigbee
import sys

class TelnetMock():
    def __init__(self):
        self.read_buffer = []
    def expect(self, regexes, timeout):
        return None, None, None
    def write(self, data):
        sys.stdout.write(data)
    def read_until(self, regex, timeout):
        return []
    def read_eager(self):
        return []

z = zigbee.ZCL(['ha.xml', 'ha12.xml'])
conn = zigbee.ZBController()
conn.conn = TelnetMock()
conn.send_zcl_command(0x1234, z.door_lock.set_p_i_n(7,1,1,4, "1234"))
