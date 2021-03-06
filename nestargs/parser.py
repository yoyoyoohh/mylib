'''
Author: Shuailin Chen
Created Date: 2020-11-21
Last Modified: 2021-07-03
	content: 
'''
import argparse
import inspect

from .meta import get_metadata


class NestedNamespace(argparse.Namespace):
    DELIMITER = "."

    def __setattr__(self, name, value):
        try:
            parent, name = name.split(self.DELIMITER, maxsplit=1)
        except ValueError:
            parent = None

        if parent:
            if not hasattr(self, parent):
                super().__setattr__(parent, NestedNamespace())
            setattr(getattr(self, parent), name, value)
        elif parent is not None:
            raise ValueError("parent should not be empty: {}".format(name))
        else:
            super().__setattr__(name, value)

    def to_flatten_dict(self, parent_key='', sep='.'):
        old_dict = vars(self)
        new_dict = {}
        for k, v in old_dict.items():
            new_key = parent_key + sep + k if parent_key else k
            # print('parent:', parent_key, '  key:', k)
            if not isinstance(v, NestedNamespace):
                new_dict.update({new_key:v})
            else:
                new_dict.update(v.to_flatten_dict(parent_key=new_key))
        return new_dict
    
    def items(self):
        ''' mimic items() func in dict class '''
        return vars(self).items()

    def to_nested_dict(self):
        old_dict = vars(self)
        new_dict = {}
        for k, v in old_dict.items():
            if not isinstance(v, NestedNamespace):
                new_dict.update({k:v})
            else:
                new_dict.update({k:v.to_nested_dict()})
        return new_dict


class NestedArgumentParser(argparse.ArgumentParser):
    def parse_known_args(self, args=None, namespace=None):
        if namespace is None:
            namespace = NestedNamespace()
        return super().parse_known_args(args=args, namespace=namespace)

    def register_arguments(self, function, prefix=None):
        if inspect.isclass(function):
            function = function.__init__
        sig = inspect.signature(function)

        if prefix:
            arg_prefix = prefix + "."
            target = self.add_argument_group(prefix)
        else:
            arg_prefix = ""
            target = self

        actions = {}
        for parameter in sig.parameters.values():
            if (
                parameter.name == "self"
                or parameter.name == "cls"
                or parameter.kind is inspect.Parameter.VAR_POSITIONAL
                or parameter.kind is inspect.Parameter.VAR_KEYWORD
                or get_metadata(function, parameter.name, "ignore")
            ):
                continue  # pragma: no cover

            name = parameter.name
            arg_params = {}
            if parameter.default is inspect.Parameter.empty:
                arg_params["required"] = True
            else:
                if parameter.default is True:
                    arg_params["action"] = "store_false"
                    arg_params["dest"] = arg_prefix + name
                    name = "no_" + name
                elif parameter.default is False:
                    arg_params["action"] = "store_true"
                elif type(parameter.default) in {int, float}:
                    arg_params["type"] = type(parameter.default)

                arg_params["default"] = parameter.default

            override_arg_params = get_metadata(function, parameter.name, "arg_params")
            if override_arg_params:
                arg_params.update(override_arg_params)

            arg_name = self.prefix_chars[0] * 2 + arg_prefix + name
            actions[parameter.name] = target.add_argument(arg_name, **arg_params)

        return actions
