#!/usr/bin/env node
/**
 * Promonta Rechnung PDF Generator — свободные позиции, шаблон по образцу RE-2026-041.
 * Вход: JSON конфиг через argv[2] (путь к файлу) или stdin.
 * Выход: путь к сгенерированному PDF (stdout, одна строка).
 */
const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');

const FIRMA = {
  name: 'Promonta Multiservice UG (haftungsbeschränkt)',
  adresse: 'Zieschestraße 37, 09111 Chemnitz, DE',
  tel: '+49 15510484398',
  steuernummer: '214/116/00103',
  iban: 'DE30 1001 8000 0386 5487 77',
  ustId: 'DE457707720',
  gf: 'Ihor Keksel (GF)',
};

const LOGO_PATH = '/home/promonta/agent/miniapp/promonta-logo.png';
const DUNKELBLAU = '#1B2B5E';
const ORANGE = '#F59E0B';
const GRAU = '#666666';

const FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';
const FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf';

function formatEuro(val) {
  const num = val.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return num + ' €'; // NBSP vor dem Eurozeichen verhindert Zeilenumbruch mitten im Betrag
}

function addDays(dateStr, days) {
  const [d, m, y] = dateStr.split('.').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + days);
  return dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function generate(config) {
  const datum = config.datum || new Date().toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const zahlungsfrist = config.zahlungsfristTage != null ? config.zahlungsfristTage : 14;
  const mwstSatz = config.mwstSatz != null ? config.mwstSatz : 19;
  const nummer = config.nummer;
  if (!nummer) throw new Error('Rechnung-Nr. fehlt');

  const positionen = config.positionen.map(p => ({
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

  const outPath = config.outPath || `/tmp/Rechnung_${nummer}.pdf`;
  const doc = new PDFDocument({ size: 'A4', margin: 0, autoFirstPage: true });

  doc.registerFont('reg', FONT_REG);
  doc.registerFont('bold', FONT_BOLD);

  const W = doc.page.width;
  const H = doc.page.height;
  const MARGIN = 50;
  const CW = W - MARGIN * 2;
  const FOOTER_H = 46;
  const CONTENT_BOTTOM = H - FOOTER_H - 10;

  function drawDiagonal(x0, y0) {
    // Оранжево-синяя диагональная лента в правом верхнем/нижнем углу, как в образце.
    doc.save();
    doc.polygon([x0, y0], [W, y0], [W, y0 + 90], [x0 + 60, y0 + 90]).fill(DUNKELBLAU);
    doc.polygon([x0 + 20, y0], [W, y0], [W, y0 + 40]).fill(ORANGE);
    doc.restore();
  }

  function drawHeader() {
    if (fs.existsSync(LOGO_PATH)) {
      doc.image(LOGO_PATH, MARGIN, 40, { width: 150 });
    } else {
      doc.font('bold').fontSize(20).fillColor(DUNKELBLAU).text('Promonta.', MARGIN, 45);
    }
    doc.font('reg').fontSize(8).fillColor(GRAU)
      .text('Innenausbau, Sanierung und Renovierung', MARGIN, 90);
    doc.moveTo(MARGIN, 108).lineTo(MARGIN + 200, 108).strokeColor(ORANGE).lineWidth(2).stroke();
    drawDiagonal(W - 140, 0);
  }

  function drawFooter() {
    const fy = H - FOOTER_H + 8;
    doc.moveTo(MARGIN, fy - 6).lineTo(W - MARGIN, fy - 6).strokeColor('#CCCCCC').lineWidth(0.5).stroke();
    doc.font('reg').fontSize(7).fillColor(GRAU).text(
      `${FIRMA.name} | ${FIRMA.adresse} | Tel.: ${FIRMA.tel}| Steuernummer: ${FIRMA.steuernummer} | IBAN: ${FIRMA.iban} | Ust-ID: ${FIRMA.ustId}`,
      MARGIN, fy, { width: CW, align: 'center' }
    );
    drawDiagonal(W - 100, H - 40);
  }

  function ensureSpace(neededHeight, y) {
    if (y + neededHeight > CONTENT_BOTTOM) {
      drawFooter();
      doc.addPage();
      drawHeader();
      return 150;
    }
    return y;
  }

  const stream = fs.createWriteStream(outPath);
  doc.pipe(stream);

  drawHeader();

  let y = 150;

  // Kunde (links) / Rechnungsdaten (rechts)
  const kunde = config.kunde || {};
  doc.font('reg').fontSize(9).fillColor('#000000');
  doc.text(`${FIRMA.name},`, MARGIN, y);
  y += 12;
  doc.font('reg').fontSize(8).fillColor(GRAU).text(FIRMA.adresse, MARGIN, y);
  y += 20;

  doc.font('bold').fontSize(10).fillColor('#000000');
  if (kunde.typ === 'firma') {
    doc.text(kunde.name || '', MARGIN, y); y += 13;
    doc.font('reg');
    if (kunde.kontakt) { doc.text(kunde.kontakt, MARGIN, y); y += 13; }
  } else {
    doc.text(`${kunde.anrede || ''} ${kunde.name || ''}`.trim(), MARGIN, y); y += 13;
    doc.font('reg');
  }
  if (kunde.adresse) { doc.text(kunde.adresse, MARGIN, y); y += 13; }
  if (kunde.typ === 'firma' && kunde.ustId) { doc.text(`Ust-ID: ${kunde.ustId}`, MARGIN, y); y += 13; }

  const rechtsLabelX = MARGIN + 280;
  const rechtsValX = MARGIN + 380;
  const rechtsValW = MARGIN + CW - rechtsValX;
  let ry = 150;
  function rechtsRow(label, value) {
    doc.font('reg').fontSize(9).fillColor('#000000').text(label, rechtsLabelX, ry, { width: rechtsValX - rechtsLabelX - 6 });
    doc.font('bold').text(value, rechtsValX, ry, { width: rechtsValW });
    ry += 16;
  }
  rechtsRow('Rechnung-Nr.:', nummer);
  if (kunde.typ === 'firma' && kunde.ustId) rechtsRow('Ust-ID:', kunde.ustId);
  rechtsRow('Erstellungsdatum:', datum);

  y = Math.max(y, ry) + 30;

  doc.font('bold').fontSize(20).fillColor(DUNKELBLAU).text('Rechnung', MARGIN, y);
  y += 32;

  if (config.projekt) {
    doc.font('bold').fontSize(9).fillColor('#000000').text('Projekt: ', MARGIN, y, { continued: true });
    doc.font('reg').text(config.projekt);
    y += 20;
  }

  const anrede = config.anredeText || 'Sehr geehrte Damen und Herren,';
  doc.font('reg').fontSize(9).fillColor('#000000').text(anrede, MARGIN, y, { width: CW });
  y += doc.heightOfString(anrede, { width: CW }) + 10;

  const introText = config.einleitung || 'vielen Dank für Ihren Auftrag und das entgegengebrachte Vertrauen. Wie vertraglich vereinbart, stelle ich Ihnen nachfolgend die bereits ausgeführten Leistungen in Rechnung.';
  doc.text(introText, MARGIN, y, { width: CW });
  y += doc.heightOfString(introText, { width: CW }) + 16;

  // Table — Spaltenbreiten großzügig, damit Beträge (z.B. "3.981,74 €") nie umbrechen.
  const colTitel = MARGIN;                 // Bezeichnung: breite Spalte
  const colMenge = MARGIN + 230;            // Menge
  const colEinheit = MARGIN + 275;          // Einheit
  const colEp = MARGIN + 330;               // Einzelpreis: genug fuer '1.234,56 EUR'
  const colBetrag = MARGIN + 410;           // Betrag: bis Seitenrand, ~85px
  const colBetragW = MARGIN + CW - colBetrag;
  const titelW = colMenge - colTitel - 8;

  function drawTableHeader(yy) {
    doc.font('bold').fontSize(9).fillColor('#000000');
    doc.text('Bezeichnung', colTitel, yy);
    doc.text('Menge', colMenge, yy);
    doc.text('Einheit', colEinheit, yy);
    doc.text('Einzelpreis', colEp, yy);
    doc.text('Betrag', colBetrag, yy, { width: colBetragW, align: 'right' });
    doc.moveTo(MARGIN, yy + 16).lineTo(MARGIN + CW, yy + 16).strokeColor('#000000').lineWidth(0.7).stroke();
    return yy + 22;
  }

  y = drawTableHeader(y);

  positionen.forEach(p => {
    const beschHeight = p.beschreibung ? doc.font('reg').fontSize(9).heightOfString(p.beschreibung, { width: titelW }) : 0;
    const rowHeight = Math.max(14, 14 + beschHeight);
    y = ensureSpace(rowHeight + 8, y);

    doc.font('reg').fontSize(9).fillColor('#000000');
    doc.text(p.titel, colTitel, y, { width: titelW });
    let by = y + 12;
    if (p.beschreibung) {
      doc.text(p.beschreibung, colTitel, by, { width: titelW });
    }
    doc.text(String(p.menge).replace('.', ','), colMenge, y, { width: colEinheit - colMenge - 4 });
    doc.text(p.einheit, colEinheit, y, { width: colEp - colEinheit - 4 });
    doc.text(formatEuro(p.epNetto), colEp, y, { width: colBetrag - colEp - 4 });
    doc.text(formatEuro(p.betragNetto), colBetrag, y, { width: colBetragW, align: 'right' });

    y += rowHeight + 8;
  });

  y = ensureSpace(80, y);
  y += 8;

  const summaryLabelX = colEp - 40;
  function summaryRow(label, value, bold) {
    doc.font(bold ? 'bold' : 'reg').fontSize(9).fillColor('#000000');
    doc.text(label, summaryLabelX, y, { width: colBetrag - summaryLabelX - 4 });
    doc.text(formatEuro(value), colBetrag, y, { width: colBetragW, align: 'right' });
    y += 15;
  }

  summaryRow('Summe (netto):', summeNetto, false);
  summaryRow(`${mwstSatz}% Ust.:`, mwst, false);
  y += 2;
  doc.moveTo(summaryLabelX, y).lineTo(MARGIN + CW, y).strokeColor('#000000').lineWidth(0.7).stroke();
  y += 6;
  summaryRow('Endbetrag (brutto):', brutto, true);

  y += 20;
  y = ensureSpace(120, y);

  const zahlungsText = `Der Gesamtbetrag beläuft sich auf ${formatEuro(brutto)}. Bitte überweisen Sie den Rechnungsbetrag innerhalb von ${zahlungsfrist} Tagen auf das unten angegebene Konto.`;
  doc.font('reg').fontSize(9).text(zahlungsText, MARGIN, y, { width: CW });
  y += doc.heightOfString(zahlungsText, { width: CW }) + 16;

  doc.text(FIRMA.name, MARGIN, y); y += 13;
  doc.text(`IBAN: ${FIRMA.iban}`, MARGIN, y); y += 13;
  doc.font('bold').text(nummer, MARGIN, y); y += 20;

  doc.font('reg').text('Für Rückfragen und weiteren Informationen stehe ich Ihnen gerne zur Verfügung.', MARGIN, y);
  y += 24;
  doc.text('Mit freundlichen Grüßen', MARGIN, y);
  y += 24;
  doc.text(FIRMA.gf, MARGIN, y); y += 13;
  doc.text('Promonta Multiservice', MARGIN, y);
  y += 20;

  // E-Signature (Фаза 7): опциональная подпись, впекается в PDF если передана.
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
