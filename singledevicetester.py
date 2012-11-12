from zigbee import ZBController
import time

class SingleDeviceTester(ZBController):
    def __init__(self):
        ZBController.__init__(self)
        self.device_under_test = None

    def wait_for_joined(self):
        self.device_under_test = ZBController.wait_for_join(self)

    def send_zcl_command(self, zcl_command):
        if not self.device_under_test:
            print "Please include a device to the network for testing"
            return
        ZBController.send_zcl_command(self, self.device_under_test, zcl_command)
        time.sleep(3)

    def read_attribute(self, attribute):
        if not self.device_under_test:
            print "Please include a device to the network for testing"
            return
        value = ZBController.read_attribute(self, self.device_under_test, attribute)
        return value

    def write_attribute(self, attribute, value):
        if not self.device_under_test:
            print "Please include a device to the network for testing"
            return
        ZBController.write_attribute(self, self.device_under_test, attribute, value)
        time.sleep(3)
