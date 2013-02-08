import unittest

class UserFacingTestCase(unittest.TestCase):
    def assertConfirmed(self, prompt):
        response = ''
        while(response == ''):
            # we append a space if the user didn't
            response = raw_input(prompt + (' ' if prompt[-1] != ' ' else ''))
        if response[0] not in 'yY':
            raise AssertionError('Failed user confirmation')
