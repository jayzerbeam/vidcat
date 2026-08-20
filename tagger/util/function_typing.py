import functools
import inspect

# use to explicity enforce types
# eg.
# @param_types(int, str)
# def func(number, string)
def param_types(*types, **kwtypes):
	def check_types(func):
		@functools.wraps(func)
		def wrapper(*args, **kw):
			for idx, t in enumerate(types):
				if not isinstance(args[idx], t):
					raise TypeError(f"argument {idx} ({type(args[idx]).__name__}) is not of type {t.__name__}")
			for k, t in kwtypes.items():
				if k in kw:
					if not isinstance(kw[k], t):
						raise TypeError(f"argument {k} ({type(kw[k]).__name__}) is not of type {t.__name__}")
			return func(*args, **kw)
		return wrapper
	return check_types

# will automatically detect types from function signature and enforce annotated types
# untested with complex variable argument functions
def enforce_types(func):
	sig = inspect.signature(func)
	@functools.wraps(func)
	def wrapper(*args, **kw):
		i = 0
		for name, param in sig.parameters.items():
			if i >= len(args):
				break
			if param.annotation != inspect._empty and not isinstance(args[i], param.annotation):
				raise TypeError(f"parameter '{name}' ({type(args[i]).__name__}) is not of type {param.annotation.__name__}")
			i += 1
		for name, v in kw.items():
			if name in sig.parameters:
				param = sig.parameters[name]
				if param.annotation != inspect._empty:
					if param.annotation == callable:
						if not callable(v):
							raise TypeError(f"named parameter '{name}' ({type(v).__name__}) is not of type {param.annotation.__name__}")
					elif not isinstance(v, param.annotation):
						raise TypeError(f"named parameter '{name}' ({type(v).__name__}) is not of type {param.annotation.__name__}")
		return func(*args, **kw)
	return wrapper

if __name__ == '__main__':
	#@param_types(str, named = int)
	@enforce_types
	def say(string:str, misc:callable, named = None):
		print(string, named)
		
	#say('first test', 3)
	say('second test', misc = lambda i, s: i, named = 1)
