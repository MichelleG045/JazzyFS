import os
import sys

CLASS_CONST = 128

def function_128(x):
    return x * 128

def helper_128(data):
    return [function_128(d) for d in data]
