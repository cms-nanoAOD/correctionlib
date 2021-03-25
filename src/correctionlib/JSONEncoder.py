#! /usr/bin/env python3
# Author: Izaak Neutelings (March 2021)
# Description: Write JSON with indents more compactly by collapsing some lists and dictionaries
# Instructions: Print or write JSON dictionary 'data' as
#   import JSONEncoder
#   print(JSONEncoder.write(data,sort_keys=True,indent=2,maxlistlen=25,maxdictlen=3,breakbrackets=False))
#   print(JSONEncoder.dumps(data,sort_keys=True,indent=2,maxlistlen=25,maxdictlen=3,breakbrackets=False))
# Adapted from:
#   https://stackoverflow.com/questions/13249415/how-to-implement-custom-indentation-when-pretty-printing-with-the-json-module
#   https://stackoverflow.com/questions/16264515/json-dumps-custom-formatting
import json, math


def write(data,fname,**kwargs):
  """Help function to quickly write JSON file formatted by JSONEncoder."""
  with open(fname,'w') as fout:
    fout.write(dumps(data,**kwargs))


def dumps(data,sort_keys=True,**kwargs):
  """Help function to quickly dump dictionary formatted by JSONEncoder."""
  if isinstance(data,(list,tuple,dict)): # for standard data structures
    return json.dumps(data,cls=JSONEncoder,sort_keys=sort_keys,**kwargs)
  else: # for pydantic
    return data.json(cls=JSONEncoder,exclude_unset=True,**kwargs)
  

class JSONEncoder(json.JSONEncoder):
  """
  Encoder to make correctionlib JSON more compact, but still readable:
  - keep list of primitives (int, float, str) on one line,
    or split over several if the length is longer than a given maxlen
  - do not break line for short dictionary if all values are primitive
  - do not break line after bracket for first key of dictionary,
    unless itself nested in dictionary
  """
  
  def __init__(self, *args, **kwargs):
    if kwargs.get('indent',None)==None:
      kwargs['indent'] = 2
    self.maxlistlen    = kwargs.pop('maxlistlen',25) # maximum of primitive elements per list, before breaking lines
    self.maxdictlen    = kwargs.pop('maxdictlen', 2) # maximum of primitive elements per dict, before breaking lines
    self.maxstrlen     = kwargs.pop('maxstrlen',2*self.maxlistlen) # maximum length of strings in short dict, before breaking lines
    self.breakbrackets = kwargs.pop('breakbrackets',False) # break after opening bracket
    super(JSONEncoder,self).__init__(*args,**kwargs)
    self._indent = 0 # current indent
    self.parent = None # type of parent for recursive use
  
  def encode(self, obj):
    grandparent = self.parent
    self.parent = type(obj)
    retval = ""
    if isinstance(obj,(list,tuple)): # lists, tuples
      output = [ ]
      if all(isinstance(x,(int,float,str)) for x in obj): # list of primitives only
        strlen = sum(len(s) for s in obj if isinstance(s,str))
        indent_str = ' '*(self._indent+self.indent)
        if strlen>self.maxstrlen and any(len(s)>3 for s in obj if isinstance(s,str)):
          obj = [json.dumps(s) for s in obj] # convert everything into a string
          if any(len(s)>self.maxstrlen/4 for s in obj): # break list of long strings into multiple lines
            output = obj
          else: # group strings into several lines
            line = [ ]
            nchars = 0
            for item in obj:
              if len(line)==0 or nchars+len(item)<self.maxstrlen:
                line.append(item)
                nchars += len(item)
              else: # new line
                output.append(", ".join(line))
                line = [item]
                nchars = len(item)
            if line:
              output.append(", ".join(line))
        elif len(obj)<=self.maxlistlen: # write short list on one line
          for item in obj:
            output.append(json.dumps(item))
          retval = "[ "+", ".join(output)+" ]"
        else: # break long list into multiple lines
          nlines = math.ceil(len(obj)/float(self.maxlistlen))
          maxlen = int(len(obj)/nlines)
          for i in range(0,nlines):
            line = [ ]
            for item in obj[i*maxlen:(i+1)*maxlen]:
              line.append(json.dumps(item))
            output.append(", ".join(line))
        if not retval:
          if grandparent==dict or self.breakbrackets: # break first line after opening bracket
            retval = "[\n"+indent_str+(",\n"+indent_str).join(output)+"\n"+' '*self._indent+"]"
          else: # do not break first line
            retval = "["+' '*(self.indent-1)+(",\n"+indent_str).join(output)+"\n"+' '*self._indent+"]"
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
      if len(obj)<=self.maxdictlen and all(isinstance(obj[k],(int,float,str)) for k in obj) and\
         sum(len(k)+len(obj[k]) for k in obj if isinstance(obj[k],str))<=self.maxstrlen: # write short dict on one line
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
      'layer2_1': {
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
      },
      'layer2_2': {
        'layer3_4': [
          ['a','b','c'],
          [l for l in 'abcdefghijklmnopqrstuvwxyz'],
          [l for l in 'abcdefghijklmnopqrstuvwxyz123'],
          [l for l in 'abcdefghijklmnopqrstuvwxyz'*2],
          ["this is short","very short",],
          ["this is medium long","verily, can you see?"],
          ["this one is a bit longer,",
           "in order to find the edge..."],
          ["this", "list of", "strings", "is a bit", "longer",
           "in order", "to find","the edge","but the","words","are short"],
          ["this", 1, 2, "list of", 45, "also", 66, "contains",
           "some", "numbers","for the", 100,"heck of","it","see if","it splits"],
          ["this", "list of strings is", "a bit longer,",
           "in order", "to find the edge..."],
          ["this is a very, very long string to test line break",
           "and this is another very long string"],
        ],
        'layer3_5': [
          list(range(1,10+1)),
          list(range(1,20+1)),
          list(range(1,24+1)),
          list(range(1,25+1)),
          list(range(1,26+1)),
          list(range(1,27+1)),
          list(range(1,30+1)),
          list(range(1,40+1)),
          list(range(1,50+1)),
          list(range(1,51+1)),
          list(range(1,52+1)),
        ],
        'layer3_6': list(range(1,20+1)),
        'layer3_7': list(range(1,40+1)),
        'layer3_8': [
          { 'key': "this is short",
            'value': "very short",
          },
          { 'key': "this is medium long",
            'value': "verily, can you see?",
          },
          { 'key': "this is one is a bit longer",
            'value': "to find the edge",
          },
          { 'key': "this is a very long string to test line break",
            'value': "another very long string",
          },
        ],
      }
    }
  }
  fname = "test_JSONEncoder.json"
  #print(json.dumps(data,cls=JSONEncoder,sort_keys=True,indent=2,
  #                      maxlistlen=25,maxdictlen=3,breakbrackets=False)) # print
  print(dumps(data,sort_keys=True,indent=2,maxlistlen=25,maxdictlen=3,breakbrackets=False)) # print
  print(f">>> Writing {fname}...")
  write(data,fname) # write
  print(f">>> Loading {fname}...")
  with open(fname) as fin: # load
    data2 = json.load(fin)
  #print(json.dumps(data2,cls=JSONEncoder,sort_keys=True,indent=2)) # print
  
