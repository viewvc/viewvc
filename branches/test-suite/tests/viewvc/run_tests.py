#!/usr/bin/env python
import sys
import os
import testutil

def do_simple_test(relurl, expected_out_file):
    cfg = testutil.setup_default_config()
    exp_data = open(os.path.join("testdata", expected_out_file), 'rb').read()
    testutil.run_and_verify_viewvc(cfg, relurl, exp_data)

def do_simple_tests(test_list):
    for test in test_list:
        do_simple_test(test[0], test[1])


def run_tests():
    do_simple_tests([
        ["cvs_main/", "cvs_main_head_directory"],
        ])
    
if __name__ == "__main__":
    run_tests()
    
