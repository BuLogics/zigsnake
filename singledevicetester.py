from zigbee import ZBController, NetworkOperationError
import time
from ConfigParser import RawConfigParser, NoSectionError, NoOptionError

class SingleDeviceTester(ZBController):
    '''
    This class is intended to take care of some of the bookkeeping when writing
    test scripts that test a single device. It takes care of including the
    device under test if it hasn't been included already. It also wraps the
    commands that interact with other ZigBee nodes and targets the device under
    test, so the test writer doesn't need to keep track of the device node ID.
    '''
    def __init__(self):
        ZBController.__init__(self)
        self.load_configs()
        if not self.controller_ip:
            self.controller_ip = raw_input("Please enter the controller IP: ")
        self.open(self.controller_ip)
        if not self.dut_node_id:
            self.wait_for_joined()
        if not self.dut_ieee_address:
            self.dut_ieee_address = raw_input(
                    "Please enter ieee address of device under test: ")
        self.save_configs()

    def load_configs(self):
        self.config_filename = 'singledevice.cfg'
        self.config = RawConfigParser()
        self.config.read(self.config_filename)
        if 'device_under_test' not in self.config.sections():
            self.config.add_section('device_under_test')
        if 'controller' not in self.config.sections():
            self.config.add_section('controller')
        self.dut_node_id = self.get_config_or_none(
                'device_under_test', 'node_id')
        if self.dut_node_id:
            self.dut_node_id = int(self.dut_node_id, 0)
        self.dut_ieee_address = self.get_config_or_none(
                'device_under_test', 'ieee_address')
        self.controller_ip = self.get_config_or_none(
                'controller', 'controller_ip')

    def get_config_or_none(self, section, option):
        if self.config.has_option(section, option):
            return self.config.get(section, option)
        else:
            return None

    def save_configs(self):
        self.config.set('controller', 'controller_ip',
                        self.controller_ip)
        self.config.set('device_under_test', 'node_id',
                        self.dut_node_id)
        self.config.set('device_under_test', 'ieee_address',
                        self.dut_ieee_address)
        with open(self.config_filename, 'w') as config_file:
            self.config.write(config_file)

    def wait_for_joined(self):
        try:
            self.enable_permit_join()
            print "Please initiate the inclusion process on the device"
            self.dut_node_id = ZBController.wait_for_join(self)
            self.disable_permit_join()
        except NetworkOperationError:
            print "Error joining device. Trying to form a new network"
            self.form_network()
            self.enable_permit_join()
            print "Please initiate the inclusion process on the device"
            self.dut_node_id = ZBController.wait_for_join(self)
            self.disable_permit_join()

    def send_zcl_command(self, zcl_command):
        ZBController.send_zcl_command(self, self.dut_node_id, zcl_command)
        time.sleep(3)

    def read_attribute(self, attribute):
        value = ZBController.read_attribute(self, self.dut_node_id, attribute)
        return value

    def write_attribute(self, attribute, value):
        ZBController.write_attribute(self, self.dut_node_id, attribute, value)
        time.sleep(4)

    def bind_node(self, cluster_id):
        ZBController.bind_node(self, self.dut_node_id,
                               self.dut_ieee_address, cluster_id)

    def configure_reporting(self, *args):
        ZBController.configure_reporting(self, self.dut_node_id, *args)

