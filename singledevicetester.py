from zigbee import ZBController, NetworkOperationError
import time
from ConfigParser import RawConfigParser, NoSectionError, NoOptionError

class SingleDeviceTester(ZBController):
    def __init__(self):
        ZBController.__init__(self)
        self.load_configs()
        if self.controller_ip is None:
            self.controller_ip = raw_input("Please enter the controller IP: ")
        self.open(self.controller_ip)
        if self.device_under_test is None:
            self.wait_for_joined()
        self.save_configs()

    def load_configs(self):
        self.config_filename = 'singledevice.cfg'
        self.config = RawConfigParser()
        self.config.read(self.config_filename)
        if 'device_under_test' not in self.config.sections():
            self.config.add_section('device_under_test')
        if 'controller' not in self.config.sections():
            self.config.add_section('controller')
        if self.config.has_option('device_under_test', 'node_id'):
            self.device_under_test = self.config.getint('device_under_test',
                                                     'node_id')
        else:
            self.device_under_test = None
        if self.config.has_option('controller', 'controller_ip'):
            self.controller_ip = self.config.get('controller',
                                                 'controller_ip')
        else:
            self.controller_ip = None

    def save_configs(self):
        self.config.set('controller', 'controller_ip',
                        self.controller_ip)
        self.config.set('device_under_test', 'node_id',
                        self.device_under_test)
        with open(self.config_filename, 'w') as config_file:
            self.config.write(config_file)

    def wait_for_joined(self):
        try:
            self.enable_permit_join()
            print "Please initiate the inclusion process on the device"
            self.device_under_test = ZBController.wait_for_join(self)
            self.disable_permit_join()
        except NetworkOperationError:
            print "Error joining device. Trying to form a new network"
            self.form_network()
            self.enable_permit_join()
            print "Please initiate the inclusion process on the device"
            self.device_under_test = ZBController.wait_for_join(self)
            self.disable_permit_join()

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
