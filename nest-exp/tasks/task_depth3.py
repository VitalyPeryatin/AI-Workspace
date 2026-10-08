"""FizzBuzz function with doctest examples."""


def fizzbuzz(n):
    """Return a list of FizzBuzz strings for numbers from 1 to n inclusive.

    Rules:
        - divisible by 3 -> "Fizz"
        - divisible by 5 -> "Buzz"
        - divisible by 3 and 5 -> "FizzBuzz"
        - otherwise -> str(number)

    >>> fizzbuzz(1)
    ['1']
    >>> fizzbuzz(3)
    ['1', '2', 'Fizz']
    >>> fizzbuzz(5)
    ['1', '2', 'Fizz', '4', 'Buzz']
    >>> fizzbuzz(15)[14]
    'FizzBuzz'
    >>> fizzbuzz(16)[15]
    '16'
    """
    result = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            result.append("FizzBuzz")
        elif i % 3 == 0:
            result.append("Fizz")
        elif i % 5 == 0:
            result.append("Buzz")
        else:
            result.append(str(i))
    return result


if __name__ == "__main__":
    import doctest

    doctest.testmod()
