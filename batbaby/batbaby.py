from collections import namedtuple

import requests
from bs4 import BeautifulSoup

url = "https://en.wikipedia.org/wiki/List_of_Batman_children's_books"

r = requests.get(url)
soup = BeautifulSoup(r.content, 'lxml')
table = soup.find("table", attrs={'class': 'wikitable'})
table_rows = table.find_all('tr', attrs={'style':'text-align: center; background:#F2F2F2;'})

Book = namedtuple('Book', ['title', 'author'])
books = []
for row in table_rows:
    title = row.find('td', attrs={'style': 'text-align: left;'}).string
    author = title.findNext('td').string
    books.append(Book(title=title, author=author))

# need to get ratings from somewhere

print(books)
