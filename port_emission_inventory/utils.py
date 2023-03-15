def m_to_nm(meters):
    return meters / 1852


class OpDict(dict):
    """
    A dictionary that can be added to and multiplied with others.

    The sum of 2 dictionaries is a new dictionary with a union of all keys.
    Values belonging to keys existing in both dictionaries are added.

    The product of 2 dictionaries is a new dictionary with the keys of the
    left-hand-side operand. Where those keys also exist in the right hand side,
    the result values are the product of both corresponding values.
    """
    def __init__(self, *args, **kwargs):
        self._start_value_factory = kwargs.pop('start_value_factory', int)
        super().__init__(*args, **kwargs)

    def __add__(self, other):
        return type(self)({
            k: self.get(k, self._start_value_factory())
            + other.get(k, self._start_value_factory())
            for k in set(self) | set(other)})

    def __mul__(self, other):
        product = {}
        for key, value in self.items():
            try:
                product[key] = value * other[key]
            except KeyError:
                product[key] = value
        return type(self)(product)
