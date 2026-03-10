import os
import sys

CLASS_CONST = 64

def function_64(x):
    return x * 64

def helper_64(data):
    return [function_64(d) for d in data]
