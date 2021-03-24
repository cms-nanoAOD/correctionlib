#! /usr/bin/env python3
# Author: Izaak Neutelings (March 2021)
# Description: Reduce number of lines in JSON by collapsing lists
# Adapted from:
#   https://stackoverflow.com/questions/13249415/how-to-implement-custom-indentation-when-pretty-printing-with-the-json-module
#   https://stackoverflow.com/questions/16264515/json-dumps-custom-formatting
import json, math


def write(data,fname,indent=2,maxlistlen=25,maxdictlen=2,breakbrackets=False):
  """Help function to quickly write JSON file."""
  with open(fname,'w') as fout:
    if isinstance(data,dict):
      fout.write(json.dumps(data,cls=JSONEncoder,sort_keys=True,indent=indent,
                 maxlistlen=maxlistlen,maxdictlen=maxdictlen,breakbrackets=breakbrackets))
    else:
      fout.write(data.json(cls=JSONEncoder,exclude_unset=True,indent=indent,
                 maxlistlen=maxlistlen,maxdictlen=maxdictlen,breakbrackets=breakbrackets))
  

class JSONEncoder(json.JSONEncoder):
  """
  Encoder to make correctionlib JSON more compact:
  - keep list of primitives (int, float, str) on one line,
    or split over several if the length is longer than a given maxlen
  - do not break line for short dictionary if all values are primitive
  - do not break line after bracket for first key of dictionary,
    unless itself nested in dictionary
  """
  
  def __init__(self, *args, **kwargs):
    self.maxlistlen    = kwargs.pop('maxlistlen',25) # maximum of primitive elements per list, before breaking lines
    self.maxdictlen    = kwargs.pop('maxdictlen',25) # maximum of primitive elements per dict, before breaking lines
    self.breakbrackets = kwargs.pop('breakbrackets',False) # break after opening bracket
    super(JSONEncoder,self).__init__(*args,**kwargs)
    self._indent = 0 # current indent
    self.parent = None # type of parent for recursive use
  
  def encode(self, obj):
    grandparent = self.parent
    self.parent = type(obj)
    if isinstance(obj,(list,tuple)): # lists, tuples
      output = [ ]
      if all(isinstance(x,(int,float,str)) for x in obj): # list of primitives only
        if len(obj)>self.maxlistlen: # break long list into multiple lines
          nlines = math.ceil(len(obj)/float(self.maxlistlen))
          maxlen = int(len(obj)/nlines)
          indent_str = ' '*(self._indent+self.indent)
          for i in range(0,nlines):
            line = [ ]
            for item in obj[i*maxlen:(i+1)*maxlen]:
              line.append(json.dumps(item))
            output.append(", ".join(line))
          if grandparent==dict or self.breakbrackets: # break first line after opening bracket
            retval = "[\n"+indent_str+(",\n"+indent_str).join(output)+"\n"+' '*self._indent+"]"
          else: # do not break first line
            retval = "["+' '*(self.indent-1)+(",\n"+indent_str).join(output)+"\n"+' '*self._indent+"]"
        else: # write short list on one line
          for item in obj:
            output.append(json.dumps(item))
          retval = "[ "+", ".join(output)+" ]"
      else: # list of lists, tuples, dictionaries
        self._indent += self.indent
        indent_str = " "*self._indent
        for item in obj:
          output.append(indent_str+self.encode(item))
        self._indent -= self.indent
        indent_str = " "*self._indent
        retval = "[\n"+",\n".join(output)+"\n"+indent_str+"]"
    elif isinstance(obj,dict): # dictionaries
      output = [ ]
      if len(obj)<=self.maxdictlen and all(isinstance(obj[k],(int,float,str)) for k in obj): # write short dict on one line
        retval = "{ "+", ".join(json.dumps(k)+": "+self.encode(obj[k]) for k in obj)+" }"
      else: # break long dict into multiple line
        self._indent += self.indent
        indent_str = " "*self._indent
        first = grandparent not in [None,dict] and not self.breakbrackets # break after opening bracket
        for key, value in obj.items():
          valstr = self.encode(value)
          if first and '\n' not in valstr: # no break between opening bracket and first key
            row = ' '*(self.indent-1)+json.dumps(key)+": "+valstr
          else: # break before key
            row = '\n'+indent_str+json.dumps(key)+": "+valstr
          output.append(row)
          first = False
        self._indent -= self.indent
        indent_str = " "*self._indent
        retval = "{"+",".join(output)+"\n"+indent_str+"}"
    else: # use default formatting
      retval = json.dumps(obj)
    self.parent = grandparent
    return retval
  

if __name__ == '__main__':
  data = { # quick test of JSONEncoder behavior
    'layer1': {
      'layer2': {
        'layer3_1': [{"x":1,"y":7}, {"x":0,"y":4}, {"x":5,"y":3},
                     {"x":6,"y":9}, {'key': 'foo', 'value': 1},
                     {'key': 'foo', 'value': {k: v for v, k in enumerate('abcd')}},
                     {k: v for v, k in enumerate('ab')},
                     {k: v for v, k in enumerate('abc')},
                     {k: v for v, k in enumerate('abcd')},
                     {k: {k2: v2 for v2, k2 in enumerate('ab')} for k in 'ab'}],
        'layer3_2': 'string',
        'layer3_3': [{"x":2,"y":8,"z":3}, {"x":1,"y":5,"z":4},
                     {"x":6,"y":9,"z":8}],
        'layer3_4': [
          list(range(10)),
          list(range(20)),
          list(range(24)),
          list(range(25)),
          list(range(26)),
          list(range(27)),
          list(range(30)),
          list(range(40)),
          list(range(50)),
          list(range(51)),
          list(range(52)),
        ],
        'layer3_5': list(range(20)),
        'layer3_6': list(range(40)),
        'layer3_7': ['a','b','c'],
      }
    }
  }
  fname = "test_JSONEncoder.json"
  print(json.dumps(data,cls=JSONEncoder,sort_keys=True,indent=2,
                        maxlistlen=25,maxdictlen=3,breakbrackets=False)) # print
  print(f">>> Writing {fname}...")
  write(data,fname) # write
  print(f">>> Loading {fname}...")
  with open(fname) as fin: # load
    data2 = json.load(fin)
  #print(json.dumps(data2,cls=JSONEncoder,sort_keys=True,indent=2)) # print
  
