# Stubs

`emmet` uses `pydantic` classes to define the data models that get built and dissemenated via the `emmet` toolkit. Many of these datatypes are built in structures in other packages that don't have the full functionality of type hints that `pydantic` would like to use. `emmet.stubs` provides fully functioning stub implementations. These classes can be used just as the original classes with all of their methods and attributes. They provide built in descriptions and schema when these data models are used for the API or validation.
