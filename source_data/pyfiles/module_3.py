import os
import sys

CLASS_CONST = 3

def function_3(x):
    return x * 3

def helper_3(data):
    return [function_3(d) for d in data]
