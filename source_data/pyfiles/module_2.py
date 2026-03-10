import os
import sys

CLASS_CONST = 2

def function_2(x):
    return x * 2

def helper_2(data):
    return [function_2(d) for d in data]
