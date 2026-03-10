import os
import sys

CLASS_CONST = 80

def function_80(x):
    return x * 80

def helper_80(data):
    return [function_80(d) for d in data]
