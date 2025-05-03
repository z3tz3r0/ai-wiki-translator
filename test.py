def lengthOfLastWord(digits: list):
    """
    :type s: str
    :rtype: int
    """
    dS = "".join(map(str,digits))
    dI = int(dS)
    dI += 1
    return [int(digit) for digit in str(dI)]





if __name__ == '__main__':
    s = [9,9]
    print(lengthOfLastWord(s))