from monty.serialization import loadfn

def load_settings(settings,default_settings):
	if os.path.is_path(settings):
		return loadfn(settings)
	elif type(settings) is dict or type(settings) is list:
		return settings
	else:
		return loadfn(default_settings)