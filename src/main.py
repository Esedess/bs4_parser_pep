import logging
import re
from collections import defaultdict
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, MAIN_PEP_URL
from exceptions import PythonVersionsException
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)

    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all('li', {'class': 'toctree-l1'})

    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)

        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append((version_link, h1.text, dl_text))

    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)

    soup = BeautifulSoup(response.text, features='lxml')

    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        error_msg = 'Не найден список версий Python.'
        logging.error(error_msg)
        raise PythonVersionsException(error_msg)

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        version = a_tag.text
        status = ''
        text_match = re.search(pattern, a_tag.text)
        if text_match:
            version, status = text_match.groups()
        results.append((link, version, status))

    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)

    soup = BeautifulSoup(response.text, features='lxml')

    main_tag = find_tag(soup, 'div', attrs={'role': 'main'})
    table_tag = find_tag(main_tag, 'table', attrs={'class': 'docutils'})

    pdf_a4_tag = find_tag(
        table_tag, 'a', attrs={'href': re.compile(r'.+pdf-a4\.zip$')}
    )

    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]

    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename

    response = session.get(archive_url)

    with open(archive_path, 'wb') as file:
        file.write(response.content)

    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = get_response(session, MAIN_PEP_URL)

    soup = BeautifulSoup(response.text, features='lxml')

    section = find_tag(soup, 'section', attrs={'id': 'numerical-index'})
    tbody = find_tag(section, 'tbody')
    tr_tags = tbody.find_all('tr')

    results = [('Status', 'Count')]
    statuses_mismatch = []
    statuses_counts = defaultdict(int)
    for pep_row in tqdm(tr_tags):
        preview_status = EXPECTED_STATUS[pep_row.next_element.text[1:]]

        pep_link = urljoin(
            MAIN_PEP_URL,
            pep_row.find('a', {'class': 'pep reference internal'})['href']
        )
        response = get_response(session, pep_link)
        soup = BeautifulSoup(response.text, features='lxml')
        dl = find_tag(soup, 'dl')
        dt_tags = dl.find_all('dt')
        for dt in dt_tags:
            if dt.text == 'Status:':
                status = dt.find_next_sibling().text
                if status not in preview_status:
                    statuses_mismatch.append(
                        (pep_link, preview_status, status)
                    )
                statuses_counts[status] += 1

    for status, count in statuses_counts.items():
        results.append((status, count))

    results.append(('', ''))
    results.append(('Total', len(tr_tags)))

    if statuses_mismatch:
        inconsistencies_text = 'Несовпадающие статусы:\n'
        for inconsistency in statuses_mismatch:
            pep_link, expected_status, received_status = inconsistency
            inconsistencies_text += (
                f'{pep_link}\n'
                f'Статус в карточке: {received_status}\n'
                f'Ожидаемые статусы: {expected_status}\n'
            )
        logging.info(inconsistencies_text)

    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION)
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
