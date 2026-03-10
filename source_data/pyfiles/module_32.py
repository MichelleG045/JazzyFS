import os
import sys

CLASS_CONST = 32

def function_32(x):
    return x * 32

def helper_32(data):
    return [function_32(d) for d in data]
