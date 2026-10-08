def fizzbuzz(n):
    """
    Возвращает список строк для чисел от 1 до n включительно по правилам FizzBuzz:
    - число делится на 3 -> "Fizz"
    - число делится на 5 -> "Buzz"
    - делится и на 3, и на 5 -> "FizzBuzz"
    - иначе -> str(число)

    >>> fizzbuzz(1)
    ['1']
    >>> fizzbuzz(3)
    ['1', '2', 'Fizz']
    >>> fizzbuzz(5)
    ['1', '2', 'Fizz', '4', 'Buzz']
    >>> fizzbuzz(15)
    ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz', '7', '8', 'Fizz', 'Buzz', '11', 'Fizz', '13', '14', 'FizzBuzz']
    >>> fizzbuzz(16)
    ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz', '7', '8', 'Fizz', 'Buzz', '11', 'Fizz', '13', '14', 'FizzBuzz', '16']
    """
    result = []
    for i in range(1, n + 1):
        if i % 3 == 0 and i % 5 == 0:
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
