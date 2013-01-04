ZigSnake
========

Introduction
------------

ZigSnake is a framework for controlling ZigBee devices from Python
scripts, with a particular emphasis on test scripts.

See http://bulogics.github.com/zigsnake-talk for introductory slides
from a talk I gave at PhillyPUG on Nov 13, 2012.

A note on nomenclature: the name 'attribute' is used both to describe
ZigBee attributes as part of the ZCL, and also attributes of a Python
object. I will try to always use ZigBee attribute to refer to the former
and Python attribute to refer to the latter.

*Note:* ZigSnake is in early phases of development and generally is
improved and fixed as we test the ZigBee products we develop. There are
some areas of the code that are in need of cleaning up and quite a few
valid use cases that it doesn't handle (such as endpoints other than 1).
Please get in touch if you're interested in contributing to make this
more production-ready.

Included Modules
----------------

### zigbee

The zigbee module gives you the ZBController class, which is your
gateway into sending and receiving ZigBee messages. Currently it
connects to an Ember ISA3, and sends messages through the Ember Command
Line Interface (CLI). To use it, simply flash an Ember development
module with a firmware image supporting the CLI.

### zcl

The zcl module defines the ZCL class, which can parse the XML files
supplied by Ember to describe the clusters in the ZigBee Cluster
Library. It is used to generate the ZCL Command and ZigBee Attribute
objects that can be used as parameters to the send_zcl_message,
expect_zcl_message, write_attribute, and read_attribute methods of the
ZBController class.

After parsing the XML files, the ZCL object has all of the clusters and
enumerated types as Python attributes. Each cluster then has all the
commands and ZigBee attributes as Python attributes. The Commands are
callable objects that take the parameters for that command. The
enumerated types have as Python attributes all the possible values for
that enumeration.

Basic Usage
-----------

    from zcl import ZCL
    from zigbee import ZBController
    from time import sleep

    z = ZCL(['general.xml', 'ha.xml', 'ha12.xml', 'ota.xml'])
    con = ZBController()
    con.open('192.168.1.134')
    con.enable_permit_join()
    device_id = con.wait_for_join()
    con.disable_permit_join()
    con.send_zcl_command( device_id, z.level_control.move_to_level(
                    desired_level, 0))
    sleep(2)
    level = con.read_attribute(device_id, z.level_control.current_level)
    print "Current level is %d" % level
