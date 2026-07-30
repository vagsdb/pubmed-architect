(() => {
  const fmt = new Intl.DateTimeFormat('el-GR');
  const num = (v) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const average = (values) => {
    const clean = values.map(num).filter((v) => v !== null);
    return clean.length ? clean.reduce((a, b) => a + b, 0) / clean.length : null;
  };
  const max = (values) => {
    const clean = values.map(num).filter((v) => v !== null);
    return clean.length ? Math.max(...clean) : null;
  };
  const min = (values) => {
    const clean = values.map(num).filter((v) => v !== null);
    return clean.length ? Math.min(...clean) : null;
  };
  const safeDate = (value) => {
    if (!value) return null;
    const d = new Date(value.length === 10 ? `${value}T12:00:00` : value);
    return Number.isNaN(d.getTime()) ? null : d;
  };
  const dateText = (value) => {
    const d = safeDate(value);
    return d ? fmt.format(d) : '—';
  };
  const yes = (v) => v === 'Ναι';
  const nonEmpty = (v) => String(v ?? '').trim().length > 0;
  const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (m) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[m]));

  function cutoffFor(period) {
    if (period === 'all') return null;
    const days = Number(period);
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - days + 1);
    return d;
  }

  function within(value, cutoff) {
    if (!cutoff) return true;
    const d = safeDate(value);
    return d ? d >= cutoff : false;
  }

  function filteredData(period) {
    const cutoff = cutoffFor(period);
    const daily = [...D.daily]
      .filter((x) => within(x.date, cutoff))
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const ae = D.ae.filter((x) => !cutoff || within(x.onset, cutoff) || within(x.reportDate, cutoff) || x.outcome === 'Σε εξέλιξη');
    const special = D.special.filter((x) => within(x.date, cutoff));
    return { cutoff, daily, ae, special, med: D.med, profile: D.profile || {} };
  }

  function buildSummary(period) {
    const { daily, ae, special, med, profile } = filteredData(period);
    const expected = daily.length * 2;
    const taken = daily.reduce((total, x) => total
      + (x.amDose && x.amDose !== 'Δεν ελήφθη' ? 1 : 0)
      + (x.pmDose && x.pmDose !== 'Δεν ελήφθη' ? 1 : 0), 0);
    const adherence = expected ? Math.round((taken / expected) * 100) : null;
    const missedDays = daily.filter((x) => x.amDose === 'Δεν ελήφθη' || x.pmDose === 'Δεν ελήφθη' || nonEmpty(x.missed)).length;
    const bowelHigh = daily.filter((x) => num(x.bowels) !== null && num(x.bowels) >= 4).length;
    const nocturnal = daily.filter((x) => yes(x.nocturnal)).length;
    const blood = daily.filter((x) => x.blood && x.blood !== 'Όχι').length;
    const vomitTotal = daily.reduce((s, x) => s + (num(x.vomiting) || 0), 0);
    const weights = daily.filter((x) => num(x.weight) !== null);
    const firstWeight = weights.length ? num(weights[0].weight) : null;
    const lastWeight = weights.length ? num(weights[weights.length - 1].weight) : null;
    const weightDelta = firstWeight !== null && lastWeight !== null ? lastWeight - firstWeight : null;
    const worseDyspnea = daily.filter((x) => x.dyspnea === 'Χειρότερη' || x.dyspnea === 'Πολύ χειρότερη').length;
    const veryWorseDyspnea = daily.filter((x) => x.dyspnea === 'Πολύ χειρότερη').length;
    const fever = daily.filter((x) => num(x.temperature) !== null && num(x.temperature) >= 38).length;
    const palpitations = daily.filter((x) => yes(x.palpitations)).length;
    const selfHarm = daily.filter((x) => yes(x.selfHarm)).length;
    const contacts = daily.filter((x) => nonEmpty(x.contact));
    const newMedsNotes = daily.filter((x) => nonEmpty(x.newMeds));
    const seriousAEs = ae.filter((x) => Object.values(x.serious || {}).some(Boolean));
    const currentMeds = med.filter((x) => !x.stop || safeDate(x.stop) >= new Date());
    const firstDate = daily.length ? daily[0].date : null;
    const lastDate = daily.length ? daily[daily.length - 1].date : null;

    const redFlags = [];
    if (selfHarm) redFlags.push(`Σκέψεις αυτοβλάβης: ${selfHarm} καταγραφή/ές`);
    if (blood) redFlags.push(`Αίμα ή μαύρα κόπρανα: ${blood} ημέρα/ες`);
    if (veryWorseDyspnea) redFlags.push(`Πολύ χειρότερη δύσπνοια: ${veryWorseDyspnea} ημέρα/ες`);
    if (seriousAEs.length) redFlags.push(`AE με κριτήριο κανονιστικής σοβαρότητας: ${seriousAEs.length}`);
    if (min(daily.map((x) => x.spo2)) !== null && min(daily.map((x) => x.spo2)) < 90) redFlags.push(`Ελάχιστο καταγεγραμμένο SpO₂ <90%`);

    const sections = [];
    sections.push({
      title: 'Στοιχεία θεραπείας',
      rows: [
        ['Patient ID', profile.patientId || '—'],
        ['Διάγνωση', profile.diagnosis || '—'],
        ['Έναρξη νεραντομιλάστης', dateText(profile.startDate)],
        ['Σχήμα', profile.regimen || '—'],
        ['Θεραπευτικό υπόβαθρο', profile.background || '—'],
        ['Περίοδος σύνοψης', firstDate && lastDate ? `${dateText(firstDate)} – ${dateText(lastDate)}` : 'Δεν υπάρχουν ημερήσιες καταγραφές'],
        ['Ημέρες με καταγραφή', String(daily.length)]
      ]
    });
    sections.push({
      title: 'Λήψη θεραπείας και συμμόρφωση',
      rows: [
        ['Καταγεγραμμένες δόσεις', `${taken}/${expected || 0}`],
        ['Εκτιμώμενη συμμόρφωση', adherence === null ? '—' : `${adherence}%`],
        ['Ημέρες με παράλειψη/καθυστέρηση/μερική δόση', String(missedDays)]
      ]
    });
    sections.push({
      title: 'Γαστρεντερική ανοχή και βάρος',
      rows: [
        ['Ημέρες με ≥4 κενώσεις', String(bowelHigh)],
        ['Μέγιστες κενώσεις/24ωρο', max(daily.map((x) => x.bowels)) ?? '—'],
        ['Νυχτερινή διάρροια', `${nocturnal} ημέρα/ες`],
        ['Αίμα ή μαύρα κόπρανα', `${blood} ημέρα/ες`],
        ['Μέση ναυτία (0–10)', average(daily.map((x) => x.nausea)) === null ? '—' : average(daily.map((x) => x.nausea)).toFixed(1)],
        ['Μέγιστη ναυτία (0–10)', max(daily.map((x) => x.nausea)) ?? '—'],
        ['Συνολικοί έμετοι', String(vomitTotal)],
        ['Βάρος αρχής περιόδου', firstWeight === null ? '—' : `${firstWeight.toFixed(1)} kg`],
        ['Βάρος τέλους περιόδου', lastWeight === null ? '—' : `${lastWeight.toFixed(1)} kg`],
        ['Μεταβολή βάρους', weightDelta === null ? '—' : `${weightDelta >= 0 ? '+' : ''}${weightDelta.toFixed(1)} kg`]
      ]
    });
    sections.push({
      title: 'Αναπνευστική και γενική κατάσταση',
      rows: [
        ['Ελάχιστο SpO₂', min(daily.map((x) => x.spo2)) === null ? '—' : `${min(daily.map((x) => x.spo2))}%`],
        ['Μέσο SpO₂', average(daily.map((x) => x.spo2)) === null ? '—' : `${average(daily.map((x) => x.spo2)).toFixed(1)}%`],
        ['Ημέρες με χειρότερη/πολύ χειρότερη δύσπνοια', String(worseDyspnea)],
        ['Ημέρες με θερμοκρασία ≥38°C', String(fever)],
        ['Ημέρες με αίσθημα παλμών/αρρυθμίας', String(palpitations)],
        ['Μέγιστη κόπωση (0–10)', max(daily.map((x) => x.fatigue)) ?? '—'],
        ['Μέγιστη ζάλη (0–10)', max(daily.map((x) => x.dizziness)) ?? '—'],
        ['Μέγιστη κεφαλαλγία (0–10)', max(daily.map((x) => x.headache)) ?? '—'],
        ['Χαμηλότερη διάθεση (0–10)', min(daily.map((x) => x.mood)) ?? '—'],
        ['Σκέψεις αυτοβλάβης', `${selfHarm} καταγραφή/ές`],
        ['Ιατρικές επικοινωνίες/ΤΕΠ/νοσηλείες', String(contacts.length)]
      ]
    });

    return {
      generatedAt: new Date(),
      profile, daily, ae, seriousAEs, special, currentMeds, contacts, newMedsNotes, redFlags, sections
    };
  }

  function summaryText(summary) {
    const lines = [];
    lines.push('ΣΥΝΟΨΗ ΗΜΕΡΟΛΟΓΙΟΥ ΘΕΡΑΠΕΙΑΣ ΜΕ ΝΕΡΑΝΤΟΜΙΛΑΣΤΗ');
    lines.push(`Δημιουργήθηκε: ${summary.generatedAt.toLocaleString('el-GR')}`);
    lines.push('');
    if (summary.redFlags.length) {
      lines.push('⚠ ΣΗΜΑΤΑ ΠΟΥ ΑΠΑΙΤΟΥΝ ΙΑΤΡΙΚΗ ΑΞΙΟΛΟΓΗΣΗ');
      summary.redFlags.forEach((x) => lines.push(`- ${x}`));
      lines.push('');
    }
    summary.sections.forEach((section) => {
      lines.push(section.title.toUpperCase());
      section.rows.forEach(([label, value]) => lines.push(`${label}: ${value}`));
      lines.push('');
    });
    lines.push(`ΑΝΕΠΙΘΥΜΗΤΑ ΣΥΜΒΑΝΤΑ (${summary.ae.length})`);
    if (!summary.ae.length) lines.push('Δεν έχουν καταγραφεί ανεπιθύμητα συμβάντα.');
    summary.ae.forEach((x, i) => {
      const serious = Object.entries(x.serious || {}).filter(([, v]) => v).map(([k]) => k).join(', ');
      lines.push(`${i + 1}. ${x.event || 'Χωρίς περιγραφή'} | Έναρξη: ${dateText(x.onset)} | Ένταση: ${x.severity || '—'} | Έκβαση: ${x.outcome || '—'} | Ενέργεια: ${x.action || '—'}${serious ? ` | Seriousness: ${serious}` : ''}`);
    });
    lines.push('');
    lines.push(`ΕΙΔΙΚΕΣ ΚΑΤΑΣΤΑΣΕΙΣ (${summary.special.length})`);
    if (!summary.special.length) lines.push('Δεν έχουν καταγραφεί ειδικές καταστάσεις.');
    summary.special.forEach((x, i) => lines.push(`${i + 1}. ${x.type || 'Άλλο'} | ${dateText(x.date)} | ${x.description || '—'} | Αναφορά: ${x.reported || '—'}`));
    lines.push('');
    lines.push(`ΤΡΕΧΟΝΤΑ ΣΥΓΧΟΡΗΓΟΥΜΕΝΑ ΦΑΡΜΑΚΑ (${summary.currentMeds.length})`);
    if (!summary.currentMeds.length) lines.push('Δεν έχουν καταγραφεί ενεργά συγχορηγούμενα φάρμακα.');
    summary.currentMeds.forEach((x, i) => lines.push(`${i + 1}. ${x.name || '—'} ${x.dose || ''} ${x.frequency || ''} | Ένδειξη: ${x.indication || '—'}`));
    lines.push('');
    if (summary.contacts.length) {
      lines.push('ΙΑΤΡΙΚΕΣ ΕΠΙΚΟΙΝΩΝΙΕΣ / ΤΕΠ / ΝΟΣΗΛΕΙΕΣ');
      summary.contacts.forEach((x) => lines.push(`- ${dateText(x.date)}: ${x.contact}`));
      lines.push('');
    }
    if (summary.newMedsNotes.length) {
      lines.push('ΝΕΑ ΦΑΡΜΑΚΑ Ή ΣΥΜΠΛΗΡΩΜΑΤΑ ΠΟΥ ΔΗΛΩΘΗΚΑΝ ΣΤΟ ΗΜΕΡΟΛΟΓΙΟ');
      summary.newMedsNotes.forEach((x) => lines.push(`- ${dateText(x.date)}: ${x.newMeds}`));
      lines.push('');
    }
    lines.push('Η σύνοψη παράγεται από τις καταγραφές του ασθενούς. Δεν αποτελεί αυτόματη αναφορά φαρμακοεπαγρύπνησης ούτε υποκαθιστά την ιατρική αξιολόγηση, την επαλήθευση, την κωδικοποίηση MedDRA ή την επίσημη υποβολή.');
    return lines.join('\n');
  }

  function summaryHtml(summary) {
    const sectionHtml = summary.sections.map((section) => `
      <section><h2>${escapeHtml(section.title)}</h2><table>${section.rows.map(([l, v]) => `<tr><th>${escapeHtml(l)}</th><td>${escapeHtml(v)}</td></tr>`).join('')}</table></section>`).join('');
    const aeHtml = summary.ae.length ? summary.ae.map((x) => {
      const serious = Object.entries(x.serious || {}).filter(([, v]) => v).map(([k]) => k).join(', ');
      return `<li><strong>${escapeHtml(x.event || 'Χωρίς περιγραφή')}</strong><br>Έναρξη: ${escapeHtml(dateText(x.onset))} · Ένταση: ${escapeHtml(x.severity || '—')} · Έκβαση: ${escapeHtml(x.outcome || '—')} · Ενέργεια: ${escapeHtml(x.action || '—')}${serious ? `<br>Seriousness: ${escapeHtml(serious)}` : ''}</li>`;
    }).join('') : '<li>Δεν έχουν καταγραφεί ανεπιθύμητα συμβάντα.</li>';
    const specialHtml = summary.special.length ? summary.special.map((x) => `<li><strong>${escapeHtml(x.type || 'Άλλο')}</strong> · ${escapeHtml(dateText(x.date))}<br>${escapeHtml(x.description || '—')}<br>Αναφορά: ${escapeHtml(x.reported || '—')}</li>`).join('') : '<li>Δεν έχουν καταγραφεί ειδικές καταστάσεις.</li>';
    const medsHtml = summary.currentMeds.length ? summary.currentMeds.map((x) => `<li>${escapeHtml(x.name || '—')} ${escapeHtml(x.dose || '')} ${escapeHtml(x.frequency || '')} · Ένδειξη: ${escapeHtml(x.indication || '—')}</li>`).join('') : '<li>Δεν έχουν καταγραφεί ενεργά συγχορηγούμενα φάρμακα.</li>';
    const alerts = summary.redFlags.length ? `<div class="alerts"><h2>⚠ Σήματα που απαιτούν ιατρική αξιολόγηση</h2><ul>${summary.redFlags.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul></div>` : '';
    return `<!doctype html><html lang="el"><head><meta charset="utf-8"><title>Σύνοψη νεραντομιλάστης</title><style>
      body{font-family:Arial,sans-serif;color:#132f3a;max-width:900px;margin:32px auto;padding:0 24px;line-height:1.45}h1{font-size:25px;margin-bottom:4px}h2{font-size:18px;margin-top:26px;border-bottom:2px solid #d7e5e8;padding-bottom:5px}.meta{color:#60747d}.alerts{background:#fff0f0;border:1px solid #d99;padding:14px;border-radius:10px}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:7px;border-bottom:1px solid #dce7e9}th{width:48%;background:#f3f7f8}li{margin-bottom:8px}.note{font-size:12px;color:#5c6d74;border-top:1px solid #ccd9dc;margin-top:30px;padding-top:12px}@media print{body{margin:0;max-width:none}.no-print{display:none}section{break-inside:avoid}}
    </style></head><body><button class="no-print" onclick="window.print()">Εκτύπωση / Αποθήκευση PDF</button><h1>Σύνοψη Ημερολογίου Θεραπείας με Νεραντομιλάστη</h1><div class="meta">Δημιουργήθηκε: ${escapeHtml(summary.generatedAt.toLocaleString('el-GR'))}</div>${alerts}${sectionHtml}<section><h2>Ανεπιθύμητα συμβάντα (${summary.ae.length})</h2><ol>${aeHtml}</ol></section><section><h2>Ειδικές καταστάσεις (${summary.special.length})</h2><ol>${specialHtml}</ol></section><section><h2>Τρέχοντα συγχορηγούμενα φάρμακα (${summary.currentMeds.length})</h2><ol>${medsHtml}</ol></section><p class="note">Η σύνοψη παράγεται από τις καταγραφές του ασθενούς. Δεν αποτελεί αυτόματη αναφορά φαρμακοεπαγρύπνησης ούτε υποκαθιστά την ιατρική αξιολόγηση, την επαλήθευση, την κωδικοποίηση MedDRA ή την επίσημη υποβολή.</p></body></html>`;
  }

  function downloadFile(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function shareSummary(summary) {
    const text = summaryText(summary);
    const id = summary.profile.patientId || 'patient';
    const file = new File([text], `nerandomilast-summary-${id}.txt`, { type: 'text/plain;charset=utf-8' });
    try {
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ title: 'Σύνοψη ημερολογίου νεραντομιλάστης', text: 'Επισυνάπτεται η σύνοψη του ημερολογίου θεραπείας.', files: [file] });
      } else if (navigator.share) {
        await navigator.share({ title: 'Σύνοψη ημερολογίου νεραντομιλάστης', text });
      } else {
        await navigator.clipboard.writeText(text);
        alert('Η σύνοψη αντιγράφηκε. Επικολλήστε την σε ασφαλές μήνυμα προς τον ιατρό.');
      }
    } catch (error) {
      if (error?.name !== 'AbortError') alert('Η κοινοποίηση δεν ολοκληρώθηκε. Χρησιμοποιήστε τη λήψη TXT ή PDF.');
    }
  }

  function init() {
    const grid = document.querySelector('#export .grid.two');
    if (!grid || document.getElementById('clinical-summary-card')) return false;
    const card = document.createElement('div');
    card.className = 'card';
    card.id = 'clinical-summary-card';
    card.innerHTML = `
      <h3>Σύνοψη για ιατρό / φαρμακοεπαγρύπνηση</h3>
      <label>Περίοδος
        <select id="summary-period">
          <option value="7">Τελευταίες 7 ημέρες</option>
          <option value="30" selected>Τελευταίες 30 ημέρες</option>
          <option value="90">Τελευταίες 90 ημέρες</option>
          <option value="all">Όλες οι καταγραφές</option>
        </select>
      </label>
      <div class="actions" style="justify-content:flex-start">
        <button type="button" id="summary-print" class="primary">Προεπισκόπηση / PDF</button>
        <button type="button" id="summary-txt" class="soft">Λήψη σύνοψης</button>
        <button type="button" id="summary-share" class="soft">Κοινοποίηση</button>
      </div>
      <p class="note">Η κοινοποίηση γίνεται μόνο όταν την επιλέξει ο ασθενής. Δεν αποστέλλονται δεδομένα αυτόματα.</p>`;
    grid.prepend(card);

    const current = () => buildSummary(document.getElementById('summary-period').value);
    document.getElementById('summary-print').onclick = () => {
      const w = window.open('', '_blank');
      if (!w) return alert('Ο browser απέκλεισε το νέο παράθυρο. Επιτρέψτε τα αναδυόμενα παράθυρα για την προεπισκόπηση.');
      w.document.open();
      w.document.write(summaryHtml(current()));
      w.document.close();
    };
    document.getElementById('summary-txt').onclick = () => {
      const s = current();
      downloadFile(`nerandomilast-summary-${s.profile.patientId || 'patient'}-${Date.now()}.txt`, summaryText(s), 'text/plain;charset=utf-8');
    };
    document.getElementById('summary-share').onclick = () => shareSummary(current());
    return true;
  }

  const timer = setInterval(() => {
    try {
      if (init()) clearInterval(timer);
    } catch (_) {
      // The encrypted diary has not been unlocked yet.
    }
  }, 300);
})();
