
(function () {
    var STILE_ID = 'dialoghi-stili-iniettati';

    function iniettaStile() {
        if (document.getElementById(STILE_ID)) return;
        var style = document.createElement('style');
        style.id = STILE_ID;
        style.textContent = `
.dlg-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,64,125,0.55);
    z-index: 3000;
    align-items: center;
    justify-content: center;
    padding: 20px;
    box-sizing: border-box;
}
.dlg-overlay.dlg-visibile { display: flex; }

.dlg-box {
    background: #FFFFFF;
    color: #16232E;
    border-radius: 10px;
    overflow: hidden;
    width: 100%;
    max-width: 440px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.35);
    font-family: 'Poppins', -apple-system, "Segoe UI", Roboto, Inter, sans-serif;
    text-align: left;
}

.dlg-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px 20px;
    background: #00407D;
    color: #FFFFFF;
    font-weight: 600;
    font-size: 1.02rem;
}
.dlg-box.dlg-pericolo .dlg-header { background: #C0553F; }
.dlg-box.dlg-info .dlg-header { background: #00407D; }

.dlg-header-icona { font-size: 1.25rem; line-height: 1; }
.dlg-header-titolo { flex: 1; margin: 0; font-size: 1.02rem; }

.dlg-body {
    padding: 20px;
    font-size: 0.98rem;
    line-height: 1.55;
    color: #16232E;
    font-weight: 500;
}

.dlg-azioni {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    padding: 14px 20px 20px;
    flex-wrap: wrap;
}

.dlg-btn {
    font-family: inherit;
    font-size: 0.92rem;
    font-weight: 600;
    padding: 10px 18px;
    border-radius: 999px;
    cursor: pointer;
    border: 1.5px solid transparent;
    min-width: 110px;
    text-align: center;
}
.dlg-btn-annulla {
    background: #FFFFFF;
    border-color: #DCE3EA;
    color: #5C6B7A;
}
.dlg-btn-annulla:hover { border-color: #00407D; color: #00407D; }

.dlg-btn-ok {
    background: #00407D;
    color: #FFFFFF;
}
.dlg-btn-ok:hover { background: #002F5C; }
.dlg-box.dlg-pericolo .dlg-btn-ok { background: #C0553F; }
.dlg-box.dlg-pericolo .dlg-btn-ok:hover { background: #a3402c; }

@media (max-width: 480px) {
    .dlg-azioni { flex-direction: column-reverse; }
    .dlg-btn { width: 100%; }
}
`;
        document.head.appendChild(style);
    }

    function iconaPerTipo(tipo) {
        if (tipo === 'pericolo') return '⚠️';
        if (tipo === 'info') return 'ℹ️';
        return '❓';
    }

    function apriDialogo(messaggio, opzioni, conBottoneAnnulla) {
        iniettaStile();
        opzioni = opzioni || {};
        var tipo = opzioni.tipo || 'domanda';

        return new Promise(function (resolve) {
            var overlay = document.createElement('div');
            overlay.className = 'dlg-overlay';

            var box = document.createElement('div');
            box.className = 'dlg-box dlg-' + tipo;

            var header = document.createElement('div');
            header.className = 'dlg-header';

            var icona = document.createElement('span');
            icona.className = 'dlg-header-icona';
            icona.textContent = iconaPerTipo(tipo);
            header.appendChild(icona);

            var titolo = document.createElement('h3');
            titolo.className = 'dlg-header-titolo';
            titolo.textContent = opzioni.titolo || (tipo === 'pericolo' ? 'Attenzione' : 'Conferma');
            header.appendChild(titolo);

            var body = document.createElement('div');
            body.className = 'dlg-body';
            body.textContent = messaggio;

            var azioni = document.createElement('div');
            azioni.className = 'dlg-azioni';

            function chiudi(risultato) {
                overlay.classList.remove('dlg-visibile');
                setTimeout(function () { overlay.remove(); }, 120);
                document.removeEventListener('keydown', suEsc);
                resolve(risultato);
            }

            function suEsc(e) {
                if (e.key === 'Escape') chiudi(false);
            }

            if (conBottoneAnnulla) {
                var btnAnnulla = document.createElement('button');
                btnAnnulla.type = 'button';
                btnAnnulla.className = 'dlg-btn dlg-btn-annulla';
                btnAnnulla.textContent = opzioni.testoAnnulla || 'Annulla';
                btnAnnulla.addEventListener('click', function () { chiudi(false); });
                azioni.appendChild(btnAnnulla);
            }

            var btnOk = document.createElement('button');
            btnOk.type = 'button';
            btnOk.className = 'dlg-btn dlg-btn-ok';
            btnOk.textContent = (conBottoneAnnulla ? opzioni.testoConferma : opzioni.testoOk) || 'OK';
            btnOk.addEventListener('click', function () { chiudi(true); });
            azioni.appendChild(btnOk);

            box.appendChild(header);
            box.appendChild(body);
            box.appendChild(azioni);
            overlay.appendChild(box);
            document.body.appendChild(overlay);

            requestAnimationFrame(function () { overlay.classList.add('dlg-visibile'); });

            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) chiudi(false);
            });
            document.addEventListener('keydown', suEsc);

            btnOk.focus();
        });
    }

    window.mostraConferma = function (messaggio, opzioni) {
        return apriDialogo(messaggio, opzioni, true);
    };

    window.mostraAvviso = function (messaggio, opzioni) {
        return apriDialogo(messaggio, opzioni, false);
    };

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.dataset.confermaGestita === '1') return;

        var messaggio = form.dataset.conferma;
        if (!messaggio) return;

        e.preventDefault();
        window.mostraConferma(messaggio, {
            titolo: form.dataset.confermaTitolo,
            tipo: form.dataset.confermaTipo || 'domanda',
            testoConferma: form.dataset.confermaOk,
            testoAnnulla: form.dataset.confermaAnnulla
        }).then(function (ok) {
            if (ok) {
                form.dataset.confermaGestita = '1';
                form.submit();
            }
        });
    });
})();