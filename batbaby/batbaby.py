from collections import namedtuple

import requests
from bs4 import BeautifulSoup

url = "https://en.wikipedia.org/wiki/List_of_Batman_children's_books"

r = requests.get(url)
soup = BeautifulSoup(r.content, 'lxml')
table = soup.find("table", attrs={'class': 'wikitable'}).find_all('tr', attrs={'style':'text-align: center; background:#F2F2F2;'})
books = []
Book = namedtuple('Book', ['title', 'author'])
for row in table:
    title = row.find('td', attrs={'style': 'text-align: left;'})
    author = title.findNext('td').string
    books.append(Book(title=title.string, author=author.string))

# need to get ratings from somewhere

print(books)
