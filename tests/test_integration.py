"""Build real master outputs, then read them through the website contracts."""
import csv
import importlib.util
import os
import tempfile
import types
import unittest
from unittest import mock

from recon import dashboard, directory, master, sectors, sources


@unittest.skipUnless(importlib.util.find_spec('duckdb'), 'needs DuckDB')
class IntegrationTests(unittest.TestCase):
    def test_build_to_dashboard_search_sector_and_export(self):
        source = dict(name='fixture', title='Fixture', licence='Synthetic', url='https://example.org')
        rows = [
            sources.record(source, '1', 'PIPE PLUMBING LTD', country='GB', postcode='SW1A 1AA',
                           category='43220 - Plumbing installation', company_number='123',
                           can_email='can email'),
            sources.record(source, '2', 'JO PLUMBER', country='GB', postcode='SW1A 1AA',
                           kind='plumbers', emails='jo@gmail.com', can_email='post only'),
        ]
        loader = types.SimpleNamespace(SOURCE=source, rows=lambda cache: iter(rows))
        with tempfile.TemporaryDirectory() as root, mock.patch.object(master, 'registry', return_value={'fixture': loader}), mock.patch.object(master, 'catalogue', return_value=[source]):
            geo = os.path.join(root, 'geo')
            os.makedirs(geo)
            master.load_source('fixture', root, root)
            db = master.combine(root, ['fixture'])
            db.close()
            master.segment(root)
            per_source, _ = master.summary(root)
            master.write_catalogue(root, per_source)
            import duckdb
            db = duckdb.connect()
            db.execute("COPY (SELECT 'SW1A1AA' AS code, 'London' AS place, 'England' AS state, 'ENG' AS state_code, 'London' AS county, 51.5 AS lat, -0.12 AS lon) TO ? (FORMAT parquet)", [os.path.join(geo, 'uk-postcodes.parquet')])
            db.close()
            finder = directory.Directory(root, geo=geo)
            self.assertTrue(finder.status()['available'])
            query = {'sector': ['trades'], 'near': ['SW1A 1AA'], 'miles': ['1']}
            found = finder.search(query)
            self.assertEqual((found['total'], found['may_email'], found['with_email'], found['placed']), (2, 1, 1, 2))
            eligible = finder.search({**query, 'rule': ['can email']})
            self.assertEqual(eligible['rows'][0]['name'], 'PIPE PLUMBING LTD')
            self.assertEqual(eligible['rows'][0]['emails'], '')
            view = dashboard.Dashboard(root).overview()
            totals = view['countries']['uk']['totals']
            self.assertEqual((totals['may_email'], totals['can_email_with_email']), (1, 0))
            self.assertEqual(view['trades'], [])  # Not produced by master build.
            cache = os.path.join(root, 'sectors')
            sectors.build(root, cache, ('uk',), geo)
            tree = sectors.Sectors(cache).tree('uk')
            trade = next(s for s in tree['sectors'] if s['sector'] == 'trades')
            self.assertEqual((trade['count'], trade['may_email']), (2, totals['may_email']))
            path = finder.export(query)
            try:
                with open(path) as handle:
                    exported = list(csv.DictReader(handle))
                self.assertEqual({r['name'] for r in exported}, {r['name'] for r in found['rows']})
                self.assertEqual({r['can_email'] for r in exported}, {'can email', 'post only'})
            finally:
                os.remove(path)

    def test_cross_country_identifiers_do_not_join(self):
        source = dict(name='fixture', licence='Synthetic', url='https://example.org')
        rows = [sources.record(source, n, 'Pipe Ltd', country=country, company_number='123',
                               website='https://pipe.example', emails='info@pipe.example')
                for n, country in enumerate(('GB', 'US'))]
        self.assertEqual(len(set(master.group(rows).values())), 2)

    def test_distinct_companies_are_not_joined_through_a_shared_listing(self):
        source = dict(name='fixture', licence='Synthetic', url='https://example.org')
        rows = [sources.record(source, n, name, country='GB', company_number=number,
                               website='https://group.example', can_email=rule)
                for n, (name, number, rule) in enumerate((
                    ('Pipe North Ltd', '123', 'can email'),
                    ('Pipe South Ltd', '456', 'can email'),
                    ('Pipe Group', '', 'post only')))]
        self.assertEqual(len(set(master.group(rows).values())), 3)

    def test_empty_and_us_only_database_status(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(directory.Directory(root).status()['available'])
            os.makedirs(os.path.join(root, 'us'))
            open(os.path.join(root, 'us', 'tx.parquet'), 'w').close()
            self.assertTrue(directory.Directory(root).status()['available'])
