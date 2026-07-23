#!/usr/bin/env node
/**
 * Promonta Angebot PDF Generator — свободные позиции (любой геверк, ручной ввод цен).
 * Вход: JSON конфиг через argv[2] (путь к файлу) или stdin.
 * Выход: путь к сгенерированному PDF (stdout, одна строка).
 */
const PDFDocument = require('pdfkit');
const fs = require('fs');

const FIRMA = {
  name: 'Promonta Multiservice UG',
  adresse: 'Zieschestraße 37, 09111 Chemnitz',
  tel: '+49 371 91909008',
  email: 'anfragen@promonta-bau.de',
  unterzeichner: 'Boris Opochitskiy',
};

const BLAU = '#1B2B5E';
const HELLBLAU = '#E8EDF5';
const GRAU = '#666666';
const HELLGRAU = '#F5F5F5';

const FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';
const FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';

function formatEuro(val) {
  return val.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
}

function generateNummer(jahr) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let id = '';
  for (let i = 0; i < 6; i++) id += chars[Math.floor(Math.random() * chars.length)];
  return `AG-${jahr}-${id}`;
}

function addDays(dateStr, days) {
  const [d, m, y] = dateStr.split('.').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + days);
  return dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function generate(config) {
  const datum = config.datum || new Date().toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const gueltigTage = config.gueltigTage != null ? config.gueltigTage : 14;
  const gueltigBis = addDays(datum, gueltigTage);
  const jahr = datum.split('.')[2];
  const nummer = generateNummer(jahr);
  const mwstSatz = config.mwstSatz != null ? config.mwstSatz : 19;
  const anzahlungPct = config.anzahlungPct != null ? config.anzahlungPct : 40;
  const fertigstellungPct = 100 - anzahlungPct;

  const positionen = config.positionen.map((p, i) => ({
    pos: `${i + 1}.`,
    titel: p.titel,
    beschreibung: p.beschreibung || '',
    menge: p.menge,
    einheit: p.einheit || 'Stk',
    epNetto: p.preis,
    betragNetto: parseFloat((p.menge * p.preis).toFixed(2)),
  }));

  const summeNetto = parseFloat(positionen.reduce((s, p) => s + p.betragNetto, 0).toFixed(2));
  const mwst = parseFloat((summeNetto * mwstSatz / 100).toFixed(2));
  const brutto = parseFloat((summeNetto + mwst).toFixed(2));
  const anzahlung = parseFloat((brutto * anzahlungPct / 100).toFixed(2));
  const fertigstellung = parseFloat((brutto - anzahlung).toFixed(2));

  const outPath = config.outPath || `/tmp/Angebot_${nummer}.pdf`;
  const doc = new PDFDocument({ size: 'A4', margin: 0, autoFirstPage: true });

  doc.registerFont('reg', FONT_REG);
  doc.registerFont('bold', FONT_BOLD);

  const W = doc.page.width;
  const H = doc.page.height;
  const MARGIN = 42;
  const CW = W - MARGIN * 2;
  const FOOTER_H = 30;
  const CONTENT_BOTTOM = H - FOOTER_H - 10;

  function drawFooter() {
    const fy = H - FOOTER_H + 6;
    doc.moveTo(MARGIN, fy - 6).lineTo(W - MARGIN, fy - 6).strokeColor('#CCCCCC').lineWidth(0.5).stroke();
    doc.font('reg').fontSize(8).fillColor(GRAU)
      .text(FIRMA.name, MARGIN, fy, { continued: true })
      .text(`    ${FIRMA.tel}`, { continued: true })
      .text(`    ${FIRMA.email}`, { align: 'right', width: CW });
  }

  function ensureSpace(neededHeight, y) {
    if (y + neededHeight > CONTENT_BOTTOM) {
      drawFooter();
      doc.addPage();
      return 40;
    }
    return y;
  }

  const stream = fs.createWriteStream(outPath);
  doc.pipe(stream);

  doc.font('reg').fontSize(8).fillColor(GRAU)
    .text(FIRMA.name, MARGIN, 32)
    .text(FIRMA.adresse, MARGIN, 42)
    .text(`Tel: ${FIRMA.tel}`, MARGIN, 52)
    .text(FIRMA.email, MARGIN, 62);

  doc.font('bold').fontSize(24).fillColor(BLAU)
    .text('Angebot', 260, 28, { width: W - 260 - MARGIN });
  doc.font('bold').fontSize(10).fillColor(BLAU)
    .text(`${nummer} | Datum: ${datum}`, 260, 62, { width: W - 260 - MARGIN });

  let y = 96;

  doc.font('bold').fontSize(10).fillColor(BLAU).text('Kunde', MARGIN, y);
  y += 14;
  doc.font('reg').fontSize(9).fillColor('#000000');
  const kunde = config.kunde || {};
  if (kunde.typ === 'firma') {
    doc.font('bold').text(kunde.name || '', MARGIN, y); y += 12;
    doc.font('reg');
    if (kunde.kontakt) { doc.text(kunde.kontakt, MARGIN, y); y += 12; }
    if (kunde.adresse) { doc.text(kunde.adresse, MARGIN, y); y += 12; }
    if (kunde.ustId) { doc.text('USt-IdNr: ' + kunde.ustId, MARGIN, y); y += 12; }
    if (kunde.email) { doc.text(kunde.email, MARGIN, y); y += 12; }
  } else {
    const kundeName = `${kunde.anrede || ''} ${kunde.name || ''}`.trim();
    if (kundeName) { doc.text(kundeName, MARGIN, y); y += 12; }
    if (kunde.adresse) { doc.text(kunde.adresse, MARGIN, y); y += 12; }
    if (kunde.email) { doc.text(kunde.email, MARGIN, y); y += 12; }
  }

  y += 8;
  if (config.objektAdresse) {
    doc.font('bold').fontSize(10).fillColor(BLAU).text('Objekt', MARGIN, y);
    y += 14;
    doc.font('reg').fontSize(9).fillColor('#000000').text(config.objektAdresse, MARGIN, y);
    y += 20;
  }

  y += 10;

  // Table header
  const colPos = MARGIN, colTitel = MARGIN + 30, colMenge = MARGIN + 300, colEinheit = MARGIN + 350,
        colEp = MARGIN + 400, colBetrag = MARGIN + 470;
  function drawTableHeader(yy) {
    doc.rect(MARGIN, yy, CW, 20).fill(BLAU);
    doc.font('bold').fontSize(8).fillColor('#FFFFFF');
    doc.text('Pos.', colPos + 4, yy + 6);
    doc.text('Leistung', colTitel, yy + 6);
    doc.text('Menge', colMenge, yy + 6);
    doc.text('Einh.', colEinheit, yy + 6);
    doc.text('EP netto', colEp, yy + 6);
    doc.text('Betrag netto', colBetrag, yy + 6, { width: MARGIN + CW - colBetrag - 4, align: 'right' });
    return yy + 20;
  }

  y = drawTableHeader(y);

  positionen.forEach((p, i) => {
    const beschHeight = p.beschreibung ? doc.font('reg').fontSize(8).heightOfString(p.beschreibung, { width: colMenge - colTitel - 6 }) : 0;
    const rowHeight = Math.max(20, 14 + beschHeight);
    y = ensureSpace(rowHeight + 4, y);
    if (y === 40) y = drawTableHeader(y);

    if (i % 2 === 1) doc.rect(MARGIN, y, CW, rowHeight).fill(HELLGRAU);

    doc.font('reg').fontSize(9).fillColor('#000000');
    doc.text(p.pos, colPos + 4, y + 4);
    doc.font('bold').fontSize(9).text(p.titel, colTitel, y + 4, { width: colMenge - colTitel - 6 });
    let by = y + 16;
    if (p.beschreibung) {
      doc.font('reg').fontSize(8).fillColor(GRAU).text(p.beschreibung, colTitel, by, { width: colMenge - colTitel - 6 });
    }
    doc.font('reg').fontSize(9).fillColor('#000000');
    doc.text(String(p.menge), colMenge, y + 4);
    doc.text(p.einheit, colEinheit, y + 4);
    doc.text(formatEuro(p.epNetto), colEp, y + 4);
    doc.text(formatEuro(p.betragNetto), colBetrag, y + 4, { width: MARGIN + CW - colBetrag - 4, align: 'right' });

    y += rowHeight + 4;
  });

  y = ensureSpace(100, y);
  y += 10;
  doc.moveTo(MARGIN, y).lineTo(MARGIN + CW, y).strokeColor('#CCCCCC').lineWidth(0.5).stroke();
  y += 10;

  function summaryRow(label, value, bold) {
    doc.font(bold ? 'bold' : 'reg').fontSize(10).fillColor(bold ? BLAU : '#000000');
    doc.text(label, MARGIN + CW - 220, y, { width: 130 });
    doc.text(formatEuro(value), MARGIN + CW - 90, y, { width: 90, align: 'right' });
    y += 16;
  }

  summaryRow('Summe netto', summeNetto, false);
  summaryRow(`zzgl. ${mwstSatz}% MwSt`, mwst, false);
  summaryRow('Gesamtbetrag brutto', brutto, true);

  y += 14;
  y = ensureSpace(80, y);
  doc.rect(MARGIN, y, CW, 60).fill(HELLBLAU);
  doc.font('bold').fontSize(9).fillColor(BLAU).text('Zahlungsbedingungen', MARGIN + 10, y + 8);
  doc.font('reg').fontSize(9).fillColor('#000000')
    .text(`Anzahlung (${anzahlungPct}%) bei Auftragserteilung: ${formatEuro(anzahlung)}`, MARGIN + 10, y + 24)
    .text(`Restzahlung (${fertigstellungPct}%) bei Fertigstellung: ${formatEuro(fertigstellung)}`, MARGIN + 10, y + 38);
  y += 70;

  y += 10;
  doc.font('reg').fontSize(9).fillColor('#000000')
    .text(`Dieses Angebot ist gültig bis ${gueltigBis}.`, MARGIN, y);
  y += 20;

  // E-Signature (Фаза 7): опциональная подпись клиента/владельца, впекается в PDF если передана.
  if (config.signatureBase64) {
    y = ensureSpace(90, y);
    const sigBuffer = Buffer.from(config.signatureBase64, 'base64');
    doc.font('reg').fontSize(9).fillColor('#000000').text('Unterschrift:', MARGIN, y);
    y += 14;
    doc.image(sigBuffer, MARGIN, y, { width: 180, height: 60, fit: [180, 60] });
    doc.moveTo(MARGIN, y + 64).lineTo(MARGIN + 180, y + 64).strokeColor('#999999').stroke();
    if (config.signedAt) {
      doc.font('reg').fontSize(7).fillColor('#666666').text(`Unterschrieben am ${config.signedAt}`, MARGIN, y + 68);
    }
    y += 90;
  }

  drawFooter();
  doc.end();

  return new Promise((resolve, reject) => {
    stream.on('finish', () => resolve(outPath));
    stream.on('error', reject);
  });
}

async function main() {
  let raw;
  if (process.argv[2]) {
    raw = fs.readFileSync(process.argv[2], 'utf-8');
  } else {
    raw = fs.readFileSync(0, 'utf-8');
  }
  const config = JSON.parse(raw);
  const outPath = await generate(config);
  console.log(outPath);
}

main().catch(e => { console.error(e); process.exit(1); });
