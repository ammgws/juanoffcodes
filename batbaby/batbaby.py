from collections import namedtuple

import click
import requests
from bs4 import BeautifulSoup

@click.command()
@click.option('--key', '-k',
              type=click.STRING,
              help='Goodreads dev API key',
             )
def main(key):
    url = "https://en.wikipedia.org/wiki/List_of_Batman_children's_books"
    ratings_url = f"https://www.goodreads.com/book/review_counts.json?key={key}&isbns="

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

    # can get ratings from goodreads but need ISBNs

    print(books)

if __name__ == "__main__":
    main()

