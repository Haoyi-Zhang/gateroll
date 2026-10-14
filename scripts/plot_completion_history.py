"""Plot retained received replies and oracle states, without rerunning RPCs."""
from pathlib import Path
import argparse
import csv
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read_history(history_path, csv_path=None):
    history = json.loads(Path(history_path).read_text(encoding='utf-8'))
    if history.get('checks_passed') is not True:
        raise ValueError('History must contain completed checked observations')
    trace = history.get('trace')
    if not isinstance(trace, list) or len(trace) != 10:
        raise ValueError('The retained sequential history has ten requests')
    rows = []
    for index, event in enumerate(trace, 1):
        transaction = event.get('transaction', {})
        reply, state = transaction.get('observed_value'), event.get('current_oracle_state')
        if type(reply) is not int or type(state) is not int or type(transaction.get('available')) is not int or transaction['available'] != 1:
            raise ValueError('An integer reply and current state are required for every received request')
        if not isinstance(event.get('label'), str) or not event['label']:
            raise ValueError('Missing request label')
        rows.append({'request': index, 'label': event['label'], 'reply': reply, 'current_expected': state})
    if csv_path is not None:
        with Path(csv_path).open(encoding='utf-8-sig', newline='') as handle:
            retained = list(csv.DictReader(handle))
        wanted = [{key: str(value) for key, value in row.items()} for row in rows]
        if retained != wanted:
            raise ValueError('Figure CSV differs from retained received observations')
    return rows


def register_body_font():
    from reportlab.pdfbase import pdfmetrics
    def located(name):
        result = subprocess.run(['kpsewhich', name], check=True, capture_output=True, text=True)
        path = Path(result.stdout.strip())
        if not result.stdout.strip() or not path.is_file():
            raise FileNotFoundError(name)
        return str(path)
    face = pdfmetrics.EmbeddedType1Face(located('utmr8a.afm'), located('utmr8a.pfb'))
    pdfmetrics.registerTypeFace(face)
    pdfmetrics.registerFont(pdfmetrics.Font('HistoryBody', face.name, 'WinAnsiEncoding'))


def draw(rows, output):
    from reportlab.pdfgen import canvas
    register_body_font()
    width, height = 420, 170
    left, bottom, plot_width, plot_height = 37, 34, 372, 103
    y_min, y_max = min(row['reply'] for row in rows) - .4, max(row['current_expected'] for row in rows) + .7
    def point(request, value):
        return left + plot_width * (request - .7) / 9.6, bottom + plot_height * (value - y_min) / (y_max - y_min)
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=True, initialFontName='HistoryBody')
    c.setFont('HistoryBody', 8.5)
    for value in sorted({row['reply'] for row in rows} | {row['current_expected'] for row in rows}):
        y = point(1, value)[1]
        c.setStrokeGray(.88)
        c.setLineWidth(.35)
        c.line(left, y, left + plot_width, y)
        c.setFillGray(0)
        c.drawRightString(left - 6, y - 2.6, str(value))
    c.setStrokeGray(0)
    c.setLineWidth(.55)
    c.line(left, bottom, left + plot_width, bottom)
    c.line(left, bottom, left, bottom + plot_height)
    for row in rows:
        x = point(row['request'], row['reply'])[0]
        c.drawCentredString(x, bottom - 12, str(row['request']))
    c.drawCentredString(left + plot_width / 2, 8, 'Completed request order')
    c.saveState()
    c.translate(10, bottom + plot_height / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, 'Counter value')
    c.restoreState()
    for boundary, label in ((4.5, 'Migration'), (6.5, 'Preference change'), (8.5, 'Proxy restart')):
        x = point(boundary, y_min)[0]
        c.setStrokeGray(.65)
        c.setLineWidth(.45)
        c.setDash(1, 2)
        c.line(x, bottom, x, bottom + plot_height)
        c.setDash()
        c.drawCentredString(x, bottom + plot_height + 3, label)
    # The oracle curve is a step function over completed request events.
    c.setStrokeColorRGB(.38, .38, .38)
    c.setLineWidth(.9)
    c.setDash(3, 2)
    path = c.beginPath()
    path.moveTo(*point(rows[0]['request'], rows[0]['current_expected']))
    for previous, row in zip(rows, rows[1:]):
        path.lineTo(*point(row['request'], previous['current_expected']))
        path.lineTo(*point(row['request'], row['current_expected']))
    c.drawPath(path)
    c.setDash()
    c.setStrokeColorRGB(.10, .29, .57)
    c.setFillColorRGB(.10, .29, .57)
    path = c.beginPath()
    for index, row in enumerate(rows):
        (path.moveTo if index == 0 else path.lineTo)(*point(row['request'], row['reply']))
    c.drawPath(path)
    for row in rows:
        c.circle(*point(row['request'], row['reply']), 2.2, stroke=1, fill=1)
    c.line(42, 159, 58, 159)
    c.circle(50, 159, 2, stroke=1, fill=1)
    c.setFillGray(0)
    c.drawString(64, 156.5, 'Received reply')
    c.setStrokeGray(.38)
    c.setDash(3, 2)
    c.line(189, 159, 205, 159)
    c.setDash()
    c.drawString(211, 156.5, 'Client current state')
    c.showPage()
    c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, default=ROOT / 'results/completion-oracle/history.json')
    parser.add_argument('--csv', type=Path, help='optional manuscript projection, checked against the retained history')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rows = read_history(args.history, args.csv)
    if args.out.exists():
        raise FileExistsError('Choose a new output; existing figures are not overwritten')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    draw(rows, args.out)
    print(json.dumps({'requests': len(rows), 'source': str(args.history), 'output': str(args.out), 'new_experiment': False}))


if __name__ == '__main__':
    main()
