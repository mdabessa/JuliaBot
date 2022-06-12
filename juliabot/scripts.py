from __future__ import annotations


import datetime
from typing import Any, Callable, List, Dict, Optional


class Script:
    index = 0
    functions: List[Dict[str, Any]] = []
    scripts: List[Script] = []

    
    def __init__(self, name: str, function_name: str, time_out: int = 60) -> None:
        func = self.__class__.fetch_function(function_name)
        if not func:
            raise Exception(f'Nenhuma função registrada com o nome "{function_name}".')

        func = func[0]

        scripts =  self.__class__.fetch_script(name, by='refname')
        if len(scripts) >= func['limit_by_name']:
            raise Exception(f'Scripts com o nome "{name}", não podem ser mais criados.')
        

        self.name = name + "_ind" + str(self.__class__.index)
        self.refname = name
        self.func = func
        #self.guild_id = guild_id
        #self.refresh = refresh
        self.last_execute = datetime.datetime.now()
        self.time_out = time_out
        self.cache = {"status": "created"}

        self.add_script(self)
        self.__class__.index += 1


    async def execute(self, *args, **kwargs):
        await self.func['function'](*args, **kwargs, cache=self.cache)
        self.last_execute = datetime.datetime.now()
        
        if self.cache['status'] == 0:
            self.close()


    def close(self):
        self.__class__.scripts.remove(self)


    @classmethod
    def function(cls, name: Optional[str] = None, events: List[str] = ['on_message'], limit_by_name: int = 1) -> Callable:
        def inner(func: Callable) -> Callable:
            _func = {}
            _func['function'] = func
            _func['events'] = events
            _func['limit_by_name'] = limit_by_name
            
            if name == None:
                _func['name'] = func.__name__
            else:
                _func['name'] = name
            
            cls.functions.append(_func)

            def wrapper(*args, **kwargs) -> None:
                func(*args, **kwargs)
            
            return wrapper

        return inner


    @classmethod
    def fetch_function(cls, query: str, by: str = 'name') -> List[Dict[str, Any]]:
        funcs = []
        for func in cls.functions:
            if by in func and func[by] == query:
                funcs.append(func)
            
        return funcs


    @classmethod
    def fetch_script(cls, query: str, by: str = "name", _in: str = "script") -> List[Script]:
        scrs = []
        if _in == "cache":
            for s in cls.get_scripts():
                try:
                    if s.cache[by] == query:
                        scrs.append(s)
                except:
                    continue
        elif _in == "script":
            for s in cls.get_scripts():
                try:
                    attr = getattr(s, by)
                    if attr == query:
                        scrs.append(s)
                    elif (query in attr) and (isinstance(attr, list)):
                        scrs.append(s)
                except:
                    continue

        elif _in == "function":
            for s in cls.get_scripts():
                try:
                    func = s.func
                    if func[by] == query:
                        scrs.append(s)
                    elif (isinstance(func[by], list)) and (query in func[by]):
                        scrs.append(s)
                except:
                    continue
        
        return scrs


    @classmethod
    def get_scripts(cls) -> List[Script]:
        return cls.scripts

    
    @classmethod
    def add_script(cls, script: Script):
        cls.scripts.append(script)
