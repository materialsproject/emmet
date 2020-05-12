# Settings Management

`emmet` has a flexible settings management system based on Pydantic's `BaseSetting`. A core `EmmetSettings` class is used to define a data model for settings. `EmmetSettings` will automatically use the `emmet_config_path` environment variable (defaults to `$HOME/.emmet.json`) to load the settings for the whole `emmet` system. By inheriting from this class, any subpackage automatically gets this core loading feature.

Example:
``` python
from pydantic import Field
from emmet.settings import EmmetSettings

class MySettings(EmmetSettings):
    my_new_setting: int = Field(3,description = "A custom setting")
```

Now any instance of `MySettings` will automatically load the configuration file and use that to initialize this setting. Using the magic of `pydantic` `BaseSettings`, these settings can also be set using environment variables prefixed by `EMMET_`.

``` bash
export EMMET_MY_NEW_SETTING=4
```
