import os
import sys

CLASS_CONST = 81

def function_81(x):
    return x * 81

def helper_81(data):
    return [function_81(d) for d in data]
