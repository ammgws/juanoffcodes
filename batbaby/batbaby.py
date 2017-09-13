from collections import namedtuple
from time import sleep

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
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'lxml')
    table = soup.find("table", attrs={'class': 'wikitable'})
    table_rows = table.find_all('tr', attrs={'style':'text-align: center; background:#F2F2F2;'})

    Book = namedtuple('Book', ['title', 'author', 'rating'])
    books = []

    with click.progressbar(table_rows) as rows:
        for row in rows:
            title = row.find('td', attrs={'style': 'text-align: left;'}).string
            author = title.findNext('td').string

            gurl = f"https://www.goodreads.com/search/index.xml?key={key}&q={title} {author}"
            r = requests.get(gurl)
            soup = BeautifulSoup(r.content, 'lxml')
            rating = soup.find('average_rating').string

            books.append(Book(title=title, author=author, rating=rating))
            sleep(1)  # to abide by Goodreads' API limits

    print(books)

if __name__ == "__main__":
    main()
