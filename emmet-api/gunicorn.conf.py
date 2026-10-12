from mp_logging import gunicorn_logconfig_dict

logconfig_dict = gunicorn_logconfig_dict(app_loggers=("emmet", "app"))
errorlog = "-"
