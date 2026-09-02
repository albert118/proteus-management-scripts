import configparser
from importlib import resources
import json
import os
from dataclasses import fields, is_dataclass
from pathlib import Path
import pprint
from platformdirs import PlatformDirs
from typing import Any, Callable, List, Optional, Type, TypeVar, cast, get_args, get_origin


T = TypeVar('T')


class HealthReportConfigParser(configparser.ConfigParser):
    """
    An advanced, fluent ConfigParser extension featuring directory hierarchies,
    strict type resolution, and automated mapping to typed dataclasses.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loaded_files: List[str] = []

    def load(self, app_name: str, app_author: str, debug=False) -> "HealthReportConfigParser":
        """
        Initialise and bootstrap the configuration from platform-specific
        common directories and local runtime overrides.
        """

        dirs = PlatformDirs(app_name, app_author)

        # dirs.user_config_dir has issues when running on a Linux server, as XDG_CONFIG_HOME will NOT be set
        # this is used by PlatformDirs to resolve the user's home directory. Without this, the directory will fall back
        # to the root user's home directory. This becomes confusing, as the expected config file will be ignored silently
        # to ensure this works as expected in a cron, preset the expected values before the cron using:

        # Intercept stripped cron environments before platformdirs initializes
        if not os.environ.get("XDG_CONFIG_HOME") and os.environ.get("HOME"):
            if (debug):
                print(f'XDG_CONFIG_HOME was not set - setting XDG_CONFIG_HOME to HOME: {os.environ.get("HOME")}')
            os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["HOME"], ".config")

        # eg. ~/config/app_name/config.ini
        user_config_path = Path(dirs.user_config_dir) / "config.ini"
        default_config_path = resources.files(app_name).joinpath("default_config.ini")

        if not user_config_path.exists():
            print(f"Default config not found. Creating default configuration at: {user_config_path}")

            # read the packaged default config and write it to the system path to create a default
            with default_config_path.open("r") as f:
                default_content = f.read()

            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(user_config_path, 'w', encoding='utf-8') as configfile:
                configfile.write(default_content)

        # allow user overrides by defining a hierarchy of configs
        config_hierarchy = [
            default_config_path,
            user_config_path,
        ]

        # Local environment override - typically for development and testing
        # only add this if the file exists, avoids confusion/extra files appearing in debug statement
        local_config_override_path = Path(__file__).parent.resolve() / ".config.local.ini"
        if local_config_override_path.exists():
            config_hierarchy.append(local_config_override_path)

        if (debug):
            print('\nResolved config paths:')
            pprint.pprint([str(p) for p in config_hierarchy], indent=2)

        self.load_hierarchy(config_hierarchy)

        return self

    def load_hierarchy(self, hierarchy: List[Path]) -> List[str]:
        """Loads a list of paths sequentially. Later entries override earlier ones."""
        paths_to_read = [str(path) for path in hierarchy]
        self.loaded_files = self.read(paths_to_read)
        return self.loaded_files

    def to_dataclass(self, cls: Type[T], debug=False) -> T:
        """
        Reflects over a top-level orchestrator dataclass, where each field name
        corresponds to an INI [section], and nested fields match options.
        """
        if not is_dataclass(cls):
            raise TypeError(f"Target class '{cls.__name__}' must be a valid @dataclass")

        section_instances = {}

        # Loop through fields of the root structural class (these represent INI [sections])
        for section_field in fields(cls):
            section_name = section_field.name

            if isinstance(section_field.type, str):
                raise TypeError(
                    f"Forward reference strings are not supported for field '{section_name}'. Ensure classes are defined before usage.")

            section_cls = cast(Type[Any], section_field.type)

            if not is_dataclass(section_cls):
                raise TypeError(f"Main configuration field '{section_name}' must map to a nested section dataclass.")

            # Extract fields for this specific INI section class
            option_kwargs = {}
            for option_field in fields(section_cls):
                option_name = option_field.name
                expected_type = option_field.type

                # Check if the key isn't explicitly defined in the file structures
                if not self.has_option(section_name, option_name):
                    # If field has a default value or default factory, let dataclass build it natively
                    if option_field.default is not option_field.default_factory or option_field.default_factory is not None:
                        continue
                    raise configparser.NoOptionError(option_name, section_name)

                # Extract and type-cast natively through our versatile runtime mapper
                option_kwargs[option_name] = self.get_typed(section_name, option_name, expected_type)

            # Instantiate the inner section dataclass object
            section_instances[section_name] = section_cls(**option_kwargs)

        # Instantiate container configuration structure wrapper
        result = cls(**section_instances)

        if (debug):
            print('\nResolved config:')
            pprint.pprint(str(result), indent=4)

        return result

    def get_clean_string(self, section: str, option: str) -> str:
        """Retrieves a string value and strips raw internal wrapping quotes (' or ")."""
        val = self.get(section, option).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1].strip()
        return val

    def getlist(self, section: str, option: str, fallback: Optional[list] = None) -> list:
        """Reads a comma-separated or JSON array string as a raw Python list."""
        if not self.has_option(section, option):
            if fallback is not None:
                return fallback
            raise configparser.NoOptionError(option, section)

        value = self.get(section, option).strip()

        if value.startswith('[') and value.endswith(']'):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        return [item.strip() for item in value.split(',') if item.strip()]

    def gettypedlist(
        self, section: str, option: str, cast_type: Callable[[Any], T], fallback: Optional[List[T]] = None
    ) -> List[T]:
        """
        Extracts a list and guarantees all items are cast to the target type.
        Usage: config.gettypedlist("Server", "ports", cast_type=int)
        """
        try:
            raw_list = self.getlist(section, option)
            if cast_type is bool:
                return cast(Any, [self._convert_to_boolean(str(i)) for i in raw_list])
            return [cast_type(item) for item in raw_list]
        except (configparser.NoOptionError, configparser.NoSectionError):
            if fallback is not None:
                return fallback
            raise
        except (ValueError, TypeError) as e:
            raise configparser.ParsingError(
                f"Failed to cast list items in section '{section}', option '{option}' to {cast_type.__name__}: {e}"
            )

    def get_typed(self, section: str, option: str, cast_type: Any) -> Any:
        """
        Resolves a scalar value or list dynamically mapped to a primitive type.
        Accepts 'Any' to circumvent strict static typing checks from runtime field reflection.
        """
        origin = get_origin(cast_type)
        if cast_type is list or origin is list:
            args = get_args(cast_type)
            item_type = args[0] if args else str

            raw_list = self.getlist(section, option)
            if item_type is bool:
                return [self._convert_to_boolean(str(i)) for i in raw_list]
            return [item_type(i) for i in raw_list]

        # Handle explicit basic primitives using native ConfigParser logic
        if cast_type is bool:
            return self.getboolean(section, option)
        if cast_type is int:
            return self.getint(section, option)
        if cast_type is float:
            return self.getfloat(section, option)

        # Fallback for paths or custom class constructors
        try:
            cleaned_value = self.get_clean_string(section, option)
            return cast_type(cleaned_value)
        except (ValueError, TypeError) as e:
            raise configparser.ParsingError(
                f"Value for '{option}' in section '{section}' cannot be cast to {cast_type}: {e}"
            )

    def _convert_to_boolean(self, value: str) -> bool:
        """Helper to match configparser's internal truth map evaluation safely."""
        val_lower = value.strip().lower().strip('"').strip("'")
        if val_lower in self.BOOLEAN_STATES:
            return self.BOOLEAN_STATES[val_lower]
        raise ValueError(f"Not a valid boolean descriptor: {value}")
