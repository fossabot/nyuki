import re

"""
Overall philosophy
dict => data processing block => dict

Detailed data flow within a data processing block
This is an object that embeds an ordered list of rules to apply.
dict => enter data processing block
     => apply 1st rule
        => extract field from dict
        => apply operation to field
        => update dict with operation's output
     => apply 2nd rule
        => ...
There can be only 1 type of rule within a data processing block
"""


# Inspired from https://github.com/faif/python-patterns/blob/master/registry.py
class _RegisteredRules(type):
    """
    This metaclass is designed to register automatically public rule classes
    that inherit from `_Rules()`.
    """
    _registry = {}

    def __new__(mcs, name, bases, attrs):
        cls = type.__new__(mcs, name, bases, attrs)
        name = cls.TYPENAME or cls.__name__.lower()
        if not name.startswith('_'):
            cls.TYPENAME = name
            mcs._registry[name] = cls
        return cls

    @classmethod
    def get(mcs):
        return mcs._registry


class _ListRules(list):
    """
    Subclass of `list()` that makes sure each element of it is an instance of
    a predefined class (e.g. `Search()`).
    """
    def __init__(self, rule_cls, *iterable):
        super(_ListRules, self).__init__()
        self._rule_cls = rule_cls
        if iterable:
            self.extend(*iterable)

    def _check_type(self, item):
        if self._rule_cls is not None and not isinstance(item, self._rule_cls):
            clsname = self._rule_cls.__name__
            raise TypeError('item is not of type {cls}'.format(cls=clsname))

    def append(self, item):
        """
        Check the object type of 'item' before appending to the list.
        """
        self._check_type(item)
        super(_ListRules, self).append(item)

    def extend(self, iterable):
        """
        Scan through 'iterable' to check object types before extending the
        list.
        """
        for item in iterable:
            self._check_type(item)
        super(_ListRules, self).extend(iterable)

    def insert(self, index, item):
        """
        Check the object type of 'item' before appending to the list.
        """
        self._check_type(item)
        super(_ListRules, self).insert(index, item)


class Converter(object):
    """
    A base class that can apply a (ordered) list of rules to a dict.
    """
    def __init__(self, rule_cls, rules=[]):
        if not issubclass(rule_cls, _Rule):
            raise TypeError('{obj} is not a subclass of _Rule'.format(
                            obj=rule_cls))
        self._rule_cls = rule_cls
        self._rules = _ListRules(rule_cls, rules)

    @property
    def type(self):
        return self._rule_cls.TYPENAME

    @property
    def rules(self):
        return self._rules

    @classmethod
    def from_dict(cls, config):
        """
        Create a `Converter()` object from dict 'config'. The dict must look
        like the following:
            {
                "type": <rule-type-name>,       # lower-case
                "rules": [
                    {"fieldname": <name>, ...}, # + rule-type dependent items
                    {"fieldname": <name>, ...},
                ]
            }
        """
        rule_cls = _RegisteredRules.get()[config['type']]
        rules = []
        for params in config['rules']:
            rules.append(rule_cls(**params))
        return cls(rule_cls, rules=rules)

    def apply(self, data):
        """
        Apply each rule sequentially to `data` (in-place update)
        """
        for rule in self.rules:
            rule.apply(data)


class _Rule(metaclass=_RegisteredRules):
    """
    A rule extracts an entry from a dict , performs an operation on the dict
    and updates the dict with the result of that operation (in-place update).
    Only one field from the input dict can be processed within a rule.
    """
    # Public subclasses of `_Rule` will have a TYPENAME attr set to classname
    # (lowercase) if not set in the subclass itself.
    TYPENAME = None

    def __init__(self, fieldname, *args, **kwargs):
        self.fieldname = fieldname
        self._configure(*args, **kwargs)

    def _configure(self, *args, **kwargs):
        """
        Configure the rule to be applied (e.g. compile a regexp) so that
        everything is ready at runtime to apply it.
        """
        raise NotImplementedError

    def apply(self, data):
        """
        Execute an operation on one field of the dict `data` and returns an
        updated dict. If no data could be processed, this method must return
        the unchanged `data` dict.
        """
        raise NotImplementedError


class _RegexpRule(_Rule):
    """
    Define a regular expression that shall be applied through several kinds of
    operations to a string.
    If the regexp pattern has named capturing parenthesis it is used to update
    the `data` dict passed to `apply()`. If a group from the match object and
    a key from `data` have the same name, the group overrides the existing
    dict value.
    """
    def _configure(self, pattern, flags=0):
        self.regexp = re.compile(pattern, flags=flags)

    def _run_regexp(self, string):
        raise NotImplementedError

    def apply(self, data):
        try:
            string = data[self.fieldname]
        except KeyError:
            # no data to process
            pass
        else:
            resdict = self._run_regexp(string)
            data.update(resdict)


class Extract(_RegexpRule):
    """
    Scan through a string looking for the first location where the regular
    expression pattern produces a match. What matters is the resulting dict of
    captured substrings.
    """
    def _configure(self, pattern, flags=0, pos=None, endpos=None):
        super(Extract, self)._configure(pattern, flags=flags)
        if not self.regexp.groupindex:
            raise TypeError("'{pattern}' has no named capturing group".format(
                            pattern=pattern))
        self._pos_args = tuple(f for f in (pos, endpos) if f is not None)

    def _run_regexp(self, string):
        args = (string,) + self._pos_args
        match = self.regexp.search(*args)
        if match is not None:
            return match.groupdict()
        else:
            return {}


class Sub(_RegexpRule):
    """
    Build a string obtained by replacing the leftmost non-overlapping
    occurrences of regexp pattern in fieldname from `data` by a replacement
    string.
    """
    def _configure(self, pattern, repl, flags=0, count=0):
        super(Sub, self)._configure(pattern, flags=flags)
        self.repl, self.count = repl, count

    def _run_regexp(self, string):
        res = self.regexp.sub(self.repl, string, count=self.count)
        return {self.fieldname: res}


class Set(_Rule):
    """
    Set or update a field in the `data` dict.
    """
    def _configure(self, value):
        self.value = value

    def apply(self, data):
        data[self.fieldname] = self.value


class Unset(_Rule):
    """
    Remove a field from the `data` dict.
    """
    def _configure(self):
        pass

    def apply(self, data):
        try:
            del data[self.fieldname]
        except KeyError:
            pass


class Lookup(_Rule):
    """
    Implements a dead-simple lookup table which perform case sensitive
    (default) or insensitive (icase=True) lookups.
    """
    def _configure(self, table={}):
        self.table = table

    def apply(self, data):
        """
        The 1st entry in the lookup table that matches the string from `data`
        replaces it. Note that entries in the lookup table are evaluated in an
        unpredictable order.
        """
        fieldval = data[self.fieldname]
        try:
            data[self.fieldname] = self.table[fieldval]
        except KeyError:
            pass
