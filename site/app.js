/* El chat de los procedimientos.
   En GitHub Pages responde con lo guardado en la evaluación (datos.json): las 74 preguntas, en la v1 y en la v2.
   Con `uv run rag servir`, la página encuentra /api/estado y pregunta en vivo a Ollama; la respuesta llega
   como líneas JSON (un paso por línea y al final la respuesta), ya escapada y con las citas resueltas. */
(() => {
  'use strict';

  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];
  const quieto = matchMedia('(prefers-reduced-motion: reduce)');
  const angosto = matchMedia('(max-width: 860px)');
  const medio = matchMedia('(max-width: 1180px)');

  // La versión de las respuestas guardadas: la mejorada (v2), salvo que el enlace pida otra (?v=v1). Cada
  // mensaje guarda la suya y puede mostrar la de la otra versión.
  const estado = { datos: null, version: 'v2', vivo: null, ocupado: false, fuenteDe: null };
  const NOMBRE = { v1: 'inicial', v2: 'mejorada' };
  const mensajes = new WeakMap(); // cada respuesta en pantalla → { r, id, version, segundos }

  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);
  const icono = (n, clase = '') => `<svg aria-hidden="true"${clase ? ` class="${clase}"` : ''}><use href="#i-${n}"/></svg>`;
  const espera = (ms) => new Promise((listo) => setTimeout(listo, quieto.matches ? 0 : ms));
  const nodo = (html) => {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  };
  const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

  const pregunta = (id) => estado.datos.porId.get(id);
  const guardada = (id, version) => estado.datos.respuestas[version][id];
  const htmlFuente = (f) => f.html ?? estado.datos.secciones[f.seccion_id];
  const nombreModelo = (m) => m.replace(/^gpt-oss:(\d+)b$/i, 'gpt-oss $1B');

  /* ---------- buscar entre las preguntas guardadas ---------- */
  const normalizar = (s) =>
    s.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();

  // Las palabras de más de tres letras, recortadas a cinco: «renueva» y «renovar» cuentan casi igual.
  const raices = (normal) => new Set(normal.split(' ').filter((w) => w.length > 3).map((w) => w.slice(0, 5)));

  function dice(a, b) {
    if (a === b) return 1;
    const pares = (s) => {
      const m = new Map();
      for (let i = 0; i < s.length - 1; i++) m.set(s.slice(i, i + 2), (m.get(s.slice(i, i + 2)) || 0) + 1);
      return m;
    };
    const pa = pares(a), pb = pares(b);
    let comunes = 0, total = 0;
    for (const [k, v] of pa) { comunes += Math.min(v, pb.get(k) || 0); total += v; }
    for (const v of pb.values()) total += v;
    return total ? (2 * comunes) / total : 0;
  }

  // Las preguntas guardadas que comparten más palabras con lo escrito.
  function parecidas(texto, n = 3) {
    const normal = normalizar(texto), propias = raices(normal);
    return estado.datos.preguntas
      .map((p) => {
        const comunes = [...propias].filter((r) => p.raices.has(r)).length;
        return [(propias.size ? comunes / propias.size : 0) + 0.3 * dice(normal, p.normal), p];
      })
      .sort((a, b) => b[0] - a[0])
      .slice(0, n)
      .map(([, p]) => p);
  }

  // ¿Las dos palabras difieren en a lo más una letra (cambiada, sobrante o faltante)? Es un error de tipeo.
  function unaLetra(a, b) {
    if (Math.abs(a.length - b.length) > 1) return false;
    let i = 0;
    while (i < a.length && a[i] === b[i]) i++;
    return a.slice(i + 1) === b.slice(i + 1) || a.slice(i) === b.slice(i + 1) || a.slice(i + 1) === b.slice(i);
  }

  // Lo escrito cuenta como una pregunta guardada solo si tiene las mismas palabras, en cualquier orden y sin
  // importar tildes ni signos. Cada número, sigla y palabra corta debe ser igual; en las palabras largas se
  // tolera un error de tipeo. Así «clase C» no es «clase B», «USD» no es «CLP», «15.000» no es «150.000» y
  // «no puedo» no es «puedo». Lo que no calza se sugiere; nunca se cambia por otra pregunta sin decirlo.
  function mismasPalabras(a, b) {
    const resto = b.split(' ');
    const propias = a.split(' ');
    if (propias.length !== resto.length) return false;
    for (const w of propias) {
      let i = resto.indexOf(w);
      if (i < 0 && w.length >= 6) i = resto.findIndex((o) => o.length >= 6 && unaLetra(w, o));
      if (i < 0) return false;
      resto.splice(i, 1);
    }
    return true;
  }

  function coincidencia(texto) {
    const normal = normalizar(texto);
    return estado.datos.preguntas.find((p) => mismasPalabras(normal, p.normal))?.id ?? null;
  }

  /* ---------- paneles ---------- */
  // En pantallas angostas, los paneles laterales se abren encima del chat. Cerrados quedan inertes (ni el
  // teclado ni un lector de pantalla llegan a ellos) y, abiertos, lo inerte es lo que queda detrás.
  let abridor = null;

  function actualizarInert() {
    const fuentes = $('#panel-fuentes'), detalle = $('#panel-detalle');
    const encima = $$('.panel.abierto').length > 0;
    fuentes.inert = medio.matches && !fuentes.classList.contains('abierto');
    detalle.inert = angosto.matches && !detalle.classList.contains('abierto');
    $('#contenido').inert = encima;
    if (!medio.matches && fuentes.classList.contains('abierto')) fuentes.inert = false;
  }

  function abrir(id) {
    if (!$(`#${id}`).classList.contains('abierto')) abridor = document.activeElement;
    for (const panel of $$('.panel.abierto')) panel.classList.remove('abierto');
    $(`#${id}`).classList.add('abierto');
    $('#velo').hidden = false;
    actualizarInert();
    $(`#${id} [data-cerrar]`)?.focus();
  }

  function cerrarTodo() {
    const habia = $$('.panel.abierto').length > 0;
    for (const panel of $$('.panel.abierto')) panel.classList.remove('abierto');
    $('#velo').hidden = true;
    actualizarInert();
    if (habia && abridor?.isConnected) abridor.focus();
    abridor = null;
  }

  function mostrarVista(nombre, abrirPanel = false) {
    for (const tab of $$('[role="tab"]')) tab.setAttribute('aria-selected', String(tab.dataset.vista === nombre));
    $('#vista-fuente').hidden = nombre !== 'fuente';
    $('#vista-evaluacion').hidden = nombre !== 'evaluacion';
    $('#detalle').scrollTop = 0;
    if (abrirPanel && angosto.matches) abrir('panel-detalle');
  }

  function marcarActiva(msg, n) {
    for (const b of $$('#mensajes [aria-pressed="true"]')) b.setAttribute('aria-pressed', 'false');
    if (msg) for (const b of $$(`[data-n="${n}"]`, msg)) b.setAttribute('aria-pressed', 'true');
  }

  function tarjeta(f, oculta = false) {
    return (
      `<button type="button" class="tarjeta${f.citada ? '' : ' sin-citar'}" data-n="${f.n}" aria-pressed="false"` +
      `${oculta ? ' hidden' : ''}><span class="fila"><span class="numero">${f.n}</span>${esc(f.codigo)}</span>` +
      `<b>${esc(f.seccion)}</b></button>`
    );
  }

  function abrirFuente(msg, n, abrirPanel = true) {
    const { r } = mensajes.get(msg);
    const f = r.fuentes.find((x) => x.n === n);
    if (!f) return;
    const otras = r.fuentes.filter((x) => x.n !== n);
    const vista = $('#vista-fuente');
    vista.innerHTML =
      `<div class="fuente-titulo"><span class="numero">${n}</span><div><h3>${esc(f.seccion)}</h3>` +
      `<p class="fuente-doc">${esc(f.documento)}</p></div></div>` +
      (f.citada ? '' : '<p class="nota-fuente">La recuperó para responder, pero la respuesta no la cita.</p>') +
      `<div class="texto">${htmlFuente(f)}</div>` +
      (f.archivo
        ? `<button type="button" class="boton-sec" data-doc="${esc(f.archivo)}">${icono('doc')}Abrir el procedimiento completo</button>`
        : '') +
      (otras.length
        ? `<div class="otras"><h4>Otras fuentes de esta respuesta</h4><div class="tarjetas">${otras.map((x) => tarjeta(x)).join('')}</div></div>`
        : '');
    estado.fuenteDe = msg;
    for (const d of $$('.doc[aria-current="true"]')) d.setAttribute('aria-current', 'false');
    marcarActiva(msg, n);
    mostrarVista('fuente', abrirPanel);
    const marca = $('mark', vista);
    if (marca) {
      const detalle = $('#detalle');
      const arriba = marca.getBoundingClientRect().top - detalle.getBoundingClientRect().top;
      if (arriba > detalle.clientHeight * 0.6) detalle.scrollTop = arriba - 120;
    }
  }

  function limpiarFuente() {
    $('#vista-fuente').innerHTML = vacioFuente;
    estado.fuenteDe = null;
    marcarActiva(null);
    if (!$('#vista-fuente').hidden) mostrarVista('evaluacion');
  }

  function abrirDocumento(archivo) {
    const d = estado.datos.documentos.find((x) => x.archivo === archivo);
    if (!d) return;
    $('#vista-fuente').innerHTML =
      (d.obsoleto
        ? `<p class="aviso">${icono('alerta')}<span>Este procedimiento está obsoleto. No se indexa, así que el asistente no lo usa para responder.</span></p>`
        : '') + `<div class="texto documento">${d.html}</div>`;
    estado.fuenteDe = null;
    for (const b of $$('.doc')) b.setAttribute('aria-current', String(b.dataset.doc === archivo));
    marcarActiva(null);
    if (medio.matches) cerrarTodo();
    mostrarVista('fuente', true);
  }

  /* ---------- la conversación ---------- */
  const conversacion = $('#conversacion');
  let pegado = true; // si el usuario no subió a leer, la conversación sigue a la respuesta
  conversacion.addEventListener('scroll', () => {
    pegado = conversacion.scrollHeight - conversacion.scrollTop - conversacion.clientHeight < 90;
  });
  const bajar = () => {
    if (pegado) conversacion.scrollTop = conversacion.scrollHeight;
  };

  // Escribe la respuesta palabra por palabra. Las citas [n] son una pieza; las etiquetas abiertas las cierra
  // el navegador en cada cuadro.
  async function escribir(el, html, animar) {
    if (!animar || quieto.matches) {
      el.innerHTML = html;
      return;
    }
    const piezas = html.match(/<button[^>]*>\d+<\/button>|<[^>]+>|[^<\s]+\s*|\s+/g) || [];
    const palabras = piezas.filter((p) => p[0] !== '<').length;
    const porCuadro = Math.max(1, Math.ceil(palabras / 30)); // a lo más unos 30 cuadros: menos de un segundo
    el.classList.add('cursor');
    let salida = '';
    for (let i = 0; i < piezas.length;) {
      for (let k = 0; i < piezas.length && k < porCuadro; i++) {
        salida += piezas[i];
        if (piezas[i][0] !== '<') k++;
      }
      el.innerHTML = salida;
      bajar();
      await espera(20);
    }
    el.classList.remove('cursor');
    el.innerHTML = html;
  }

  function pasos(msg, texto, girando = true) {
    let p = $('.pasos', msg);
    if (!p) {
      p = nodo('<div class="pasos"><svg></svg><span></span><small></small></div>');
      msg.prepend(p);
    }
    p.firstElementChild.outerHTML = girando ? icono('cargando', 'girando') : icono('buscar');
    p.children[1].textContent = texto;
    return p;
  }

  function meta(r, info) {
    const lineas = [];
    if (info.id) {
      const p = pregunta(info.id);
      lineas.push(
        r.correcta
          ? `<div class="ok">${icono('ok')}<span><b>Correcta en la evaluación.</b> ${esc(p.esperado)}</span></div>`
          : `<div class="mal">${icono('mal')}<span><b>Incorrecta en la evaluación.</b> ${esc(p.esperado)}</span></div>`,
      );
    }
    // La comprobación de citas: una etiqueta corta; lo que se revisó exactamente, al abrirla.
    const { tipo, texto, detalle } = r.estado;
    lineas.push(
      detalle
        ? `<div class="${tipo}">${icono(tipo)}<details><summary>${esc(texto)}</summary><p>${esc(detalle)}</p></details></div>`
        : `<div class="${tipo}">${icono(tipo)}<span>${esc(texto)}.</span></div>`,
    );
    let html = `<div class="meta">${lineas.join('')}</div>`;
    if (info.id && r.aviso) {
      html +=
        `<p class="aviso">${icono('alerta')}<span>La comprobación de citas pasó y aun así la respuesta es incorrecta: ` +
        'la frase citada existe en la fuente, pero no responde lo que se preguntó. Es el límite del validador.</span></p>';
    }
    if (info.id) {
      const otra = info.version === 'v2' ? 'v1' : 'v2';
      html +=
        `<div class="acciones"><button type="button" class="enlace" data-otra="${otra}">` +
        `Ver lo que respondió la versión ${NOMBRE[otra]}</button></div>`;
    }
    return html;
  }

  async function pintarRespuesta(msg, r, info, animar) {
    mensajes.set(msg, { r, ...info });
    const docs = new Set(r.fuentes.map((f) => f.documento)).size;
    const citadas = r.fuentes.filter((f) => f.citada);
    const resto = r.fuentes.filter((f) => !f.citada);
    const mas = resto.length
      ? `<button type="button" class="tarjeta mas" aria-expanded="false">${
          citadas.length ? `+${resto.length} sin citar` : `Ver las ${resto.length} secciones que revisó`
        }</button>`
      : '';
    // De dónde viene la respuesta queda escrito en cada mensaje: guardada en la evaluación (y de qué versión) o
    // recién hecha por el modelo en este computador.
    const origen = info.id
      ? `<span class="origen">Guardada, versión ${NOMBRE[info.version]}</span><span>Revisó `
      : '<span class="origen vivo">En vivo</span><span>Revisó ';
    const tiempo =
      info.segundos == null ? '' : `<small>${info.segundos} s${info.id ? ' en la evaluación' : ''}</small>`;
    msg.innerHTML =
      `<div class="pasos hecho">${origen}${plural(r.fuentes.length, 'sección', 'secciones')} de ` +
      `${plural(docs, 'procedimiento', 'procedimientos')}</span>${tiempo}</div>` +
      `<div class="tarjetas">${citadas.map((f) => tarjeta(f)).join('')}${resto.map((f) => tarjeta(f, true)).join('')}${mas}</div>` +
      '<div class="respuesta"></div>';
    await escribir($('.respuesta', msg), r.html, animar);
    msg.insertAdjacentHTML('beforeend', meta(r, info));
    bajar();
    // En pantallas anchas, la fuente citada se abre sola al lado. Si el panel mostraba esta misma respuesta
    // (al cambiar de versión), se actualiza aunque el panel esté cerrado.
    const mismo = estado.fuenteDe === msg;
    if (citadas.length && (mismo || !angosto.matches)) abrirFuente(msg, citadas[0].n, false);
    else if (mismo || (estado.fuenteDe && !angosto.matches)) limpiarFuente();
  }

  // Una respuesta guardada se muestra de inmediato: no se simulan pasos de búsqueda que no ocurrieron ahora.
  async function mostrarGuardada(msg, id, version, animar) {
    const r = guardada(id, version);
    await pintarRespuesta(msg, r, { id, version, segundos: r.segundos }, animar);
    history.replaceState(null, '', `?p=${id}&v=${version}`);
  }

  async function sugerir(msg, texto) {
    const opciones = parecidas(texto)
      .map((p) => `<button type="button" class="opcion" data-id="${p.id}">${esc(p.texto)}</button>`)
      .join('');
    msg.innerHTML = '<div class="respuesta"></div>';
    await escribir(
      $('.respuesta', msg),
      `<p>Aquí no está corriendo el modelo, así que solo tengo las respuestas de las ${estado.datos.preguntas.length} ` +
        'preguntas de la evaluación. Ninguna es igual a lo que escribiste; estas son las más parecidas:</p>',
      true,
    );
    msg.insertAdjacentHTML(
      'beforeend',
      `<div class="opciones">${opciones}</div><p class="nota-opciones">Para preguntar cualquier cosa, ` +
        `<a href="${esc($('#nota-redactor a')?.href || '#')}">córrelo en tu computador con Ollama</a>.</p>`,
    );
    bajar();
  }

  async function enVivo(msg, texto) {
    const inicio = performance.now();
    const p = pasos(msg, 'Enviando la pregunta al modelo');
    const reloj = setInterval(() => {
      $('small', p).textContent = `${Math.round((performance.now() - inicio) / 1000)} s`;
    }, 1000);
    let respondio = false;
    try {
      const res = await fetch('api/preguntar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: texto }),
      });
      if (!res.ok || !res.body) throw new Error(`el servidor respondió ${res.status}`);
      const lector = res.body.getReader();
      const decodificador = new TextDecoder();
      let resto = '';
      for (;;) {
        const { value, done } = await lector.read();
        if (done) break;
        resto += decodificador.decode(value, { stream: true });
        let corte;
        while ((corte = resto.indexOf('\n')) >= 0) {
          const linea = resto.slice(0, corte).trim();
          resto = resto.slice(corte + 1);
          if (!linea) continue;
          const evento = JSON.parse(linea);
          if (evento.tipo === 'paso') pasos(msg, evento.texto);
          else if (evento.tipo === 'error') throw new Error(evento.texto);
          else if (evento.tipo === 'respuesta') {
            clearInterval(reloj);
            respondio = true;
            await pintarRespuesta(msg, evento.respuesta, { segundos: evento.respuesta.segundos }, true);
          }
        }
      }
      if (!respondio) throw new Error('Se cortó la conexión con el servidor antes de la respuesta.');
    } catch (error) {
      const texto = String(error.message || error);
      msg.innerHTML = `<p class="error">${icono('alerta')}<span>${esc(texto.startsWith('No pude') ? texto : `No pude responder: ${texto}`)}</span></p>`;
    } finally {
      clearInterval(reloj);
    }
  }

  async function preguntar(texto, opciones = {}) {
    if (estado.ocupado || !estado.datos) return;
    estado.ocupado = true;
    actualizarEnviar();
    $('#inicio').hidden = true;
    const lista = $('#mensajes');
    const usuario = nodo('<div class="msg msg-usuario"><p></p></div>');
    usuario.firstElementChild.textContent = texto;
    const msg = nodo('<article class="msg msg-asistente" aria-busy="true"></article>');
    lista.append(usuario, msg);
    pegado = true;
    bajar();
    try {
      if (estado.vivo && !opciones.id) await enVivo(msg, texto);
      else {
        const id = opciones.id || coincidencia(texto);
        if (id) await mostrarGuardada(msg, id, opciones.version || estado.version, true);
        else await sugerir(msg, texto);
      }
    } finally {
      msg.removeAttribute('aria-busy');
      estado.ocupado = false;
      actualizarEnviar();
    }
  }

  function nueva() {
    if (estado.ocupado) return;
    $('#mensajes').innerHTML = '';
    $('#inicio').hidden = false;
    limpiarFuente();
    for (const d of $$('.doc[aria-current="true"]')) d.setAttribute('aria-current', 'false');
    mostrarVista('evaluacion');
    history.replaceState(null, '', location.pathname);
    caja.focus();
  }

  /* ---------- lo que se pinta una vez ---------- */
  function pintarDocumentos() {
    const { documentos, areas } = estado.datos;
    $('#lista-documentos').innerHTML = areas
      .filter((a) => documentos.some((d) => d.area === a))
      .map(
        (a) =>
          `<div class="grupo"><h3>${esc(a)}</h3>${documentos
            .filter((d) => d.area === a)
            .map(
              (d) =>
                `<button type="button" class="doc" data-doc="${esc(d.archivo)}" aria-current="false">${icono('doc')}` +
                `<span><b>${esc(d.codigo)}</b><small>${esc(d.titulo)}</small>` +
                `${d.obsoleto ? '<em class="etiqueta">Obsoleto</em>' : ''}</span></button>`,
            )
            .join('')}</div>`,
      )
      .join('');
  }

  function pintarSugerencias() {
    $('#sugerencias').innerHTML = estado.datos.destacadas
      .map(
        ({ id, etiqueta }) =>
          `<button type="button" class="sugerencia" data-id="${id}"><small>${esc(etiqueta)}</small>` +
          `<span>${esc(pregunta(id).texto)}</span></button>`,
      )
      .join('');
  }

  function pintarLista(filtro) {
    const q = normalizar(filtro);
    const grupos = estado.datos.areas
      .map((a) => [a, estado.datos.preguntas.filter((p) => p.area === a && (!q || p.normal.includes(q)))])
      .filter(([, ps]) => ps.length);
    $('#lista-preguntas').innerHTML = grupos.length
      ? grupos
          .map(
            ([a, ps]) =>
              `<h3>${esc(a)}</h3>${ps
                .map((p) => `<button type="button" class="pregunta-lista" data-id="${p.id}">${esc(p.texto)}</button>`)
                .join('')}`,
          )
          .join('')
      : `<p class="vacio">Ninguna pregunta contiene «${esc(filtro)}».</p>`;
  }

  async function revisarVivo() {
    try {
      const res = await fetch('api/estado', { cache: 'no-store' });
      if (!res.ok) return; // GitHub Pages: no hay API
      const e = await res.json();
      if (e.vivo) {
        estado.vivo = e;
        $('#alcance').textContent =
          `El modelo corre en este computador, con Ollama: puedes preguntar lo que quieras sobre los ` +
          `${estado.datos.documentos.length} procedimientos de esta mina ficticia. Los ejemplos se responden en vivo.`;
        const pastilla = $('#en-vivo');
        pastilla.textContent = `En vivo con ${nombreModelo(e.modelo)}`;
        pastilla.hidden = false;
        $('#nota-redactor').textContent =
          `Responde ${nombreModelo(e.modelo)} en este computador, sin internet. Cada pregunta se responde por ` +
          'separado y toma cerca de medio minuto.';
      } else if (e.motivo) {
        $('#nota-redactor').textContent = `${e.motivo} Mientras tanto, responde con lo guardado de la evaluación.`;
      }
    } catch {
      /* sin servidor */
    }
  }

  /* ---------- eventos ---------- */
  const caja = $('#pregunta');
  const enviar = $('.enviar');
  const vacioFuente = $('#vista-fuente').innerHTML;
  const dialogo = $('#todas');

  function actualizarEnviar() {
    enviar.disabled = estado.ocupado || !caja.value.trim();
    $('#nueva').disabled = estado.ocupado;
  }

  function ajustarCaja() {
    caja.style.height = 'auto';
    caja.style.height = `${Math.min(caja.scrollHeight, 160)}px`;
  }

  caja.addEventListener('input', () => {
    ajustarCaja();
    actualizarEnviar();
  });
  caja.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $('#redactor').requestSubmit();
    }
  });
  $('#redactor').addEventListener('submit', (e) => {
    e.preventDefault();
    const texto = caja.value.trim();
    if (!texto || estado.ocupado) return;
    caja.value = '';
    ajustarCaja();
    preguntar(texto);
  });

  $('#mensajes').addEventListener('click', (e) => {
    const msg = e.target.closest('.msg-asistente');
    const boton = e.target.closest('button');
    if (!msg || !boton) return;
    if (boton.matches('.cita, .tarjeta[data-n]')) abrirFuente(msg, Number(boton.dataset.n));
    else if (boton.matches('.tarjeta.mas')) {
      const abierto = boton.getAttribute('aria-expanded') !== 'true';
      for (const t of $$('.tarjeta.sin-citar', msg)) t.hidden = !abierto;
      boton.setAttribute('aria-expanded', String(abierto));
      const total = $$('.tarjeta.sin-citar', msg).length;
      const citadas = $$('.tarjeta[data-n]:not(.sin-citar)', msg).length;
      boton.textContent = abierto ? 'Ocultar' : citadas ? `+${total} sin citar` : `Ver las ${total} secciones que revisó`;
    } else if (boton.matches('.opcion')) preguntar(pregunta(boton.dataset.id).texto, { id: boton.dataset.id });
    else if (boton.dataset.otra && !estado.ocupado) mostrarGuardada(msg, mensajes.get(msg).id, boton.dataset.otra, false);
  });

  $('#detalle').addEventListener('click', (e) => {
    const boton = e.target.closest('button');
    if (!boton) return;
    if (boton.dataset.doc) abrirDocumento(boton.dataset.doc);
    else if (boton.matches('.tarjeta[data-n]') && estado.fuenteDe) abrirFuente(estado.fuenteDe, Number(boton.dataset.n));
  });

  // «Ver un error conocido» y «Ver ese caso»: siempre la respuesta guardada, también en vivo, porque muestran
  // lo que pasó en la evaluación.
  document.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-preguntar]');
    if (!boton || !estado.datos) return;
    const p = pregunta(boton.dataset.preguntar);
    if (angosto.matches) cerrarTodo();
    preguntar(p.texto, { id: p.id, version: boton.dataset.conVersion });
  });

  $('#lista-documentos').addEventListener('click', (e) => {
    const boton = e.target.closest('.doc');
    if (boton) abrirDocumento(boton.dataset.doc);
  });

  $('#sugerencias').addEventListener('click', (e) => {
    const boton = e.target.closest('.sugerencia');
    if (boton) preguntar(pregunta(boton.dataset.id).texto, { id: estado.vivo ? undefined : boton.dataset.id });
  });

  $('#ver-todas').addEventListener('click', () => {
    $('#filtro').value = '';
    pintarLista('');
    dialogo.showModal();
  });
  $('#filtro').addEventListener('input', (e) => pintarLista(e.target.value));
  $('[data-cerrar-dialogo]').addEventListener('click', () => dialogo.close());
  dialogo.addEventListener('click', (e) => {
    if (e.target === dialogo) dialogo.close(); // clic en el fondo
    const boton = e.target.closest('.pregunta-lista');
    if (boton) {
      dialogo.close();
      preguntar(pregunta(boton.dataset.id).texto, { id: estado.vivo ? undefined : boton.dataset.id });
    }
  });

  for (const tab of $$('[role="tab"]')) tab.addEventListener('click', () => mostrarVista(tab.dataset.vista));
  $('#nueva').addEventListener('click', nueva);
  for (const b of $$('[data-abrir]')) {
    b.addEventListener('click', () => {
      if (b.dataset.abrir === 'panel-detalle') mostrarVista('evaluacion');
      abrir(b.dataset.abrir);
    });
  }
  for (const b of $$('[data-cerrar]')) b.addEventListener('click', cerrarTodo);
  actualizarInert();
  $('#velo').addEventListener('click', cerrarTodo);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !dialogo.open) cerrarTodo();
  });
  angosto.addEventListener('change', cerrarTodo);
  medio.addEventListener('change', cerrarTodo);

  /* ---------- inicio ---------- */
  async function iniciar() {
    try {
      const res = await fetch('datos.json');
      if (!res.ok) throw new Error(res.status);
      estado.datos = await res.json();
    } catch {
      $('#inicio').hidden = true;
      $('#mensajes').innerHTML =
        `<p class="error">${icono('alerta')}<span>No pude cargar las respuestas (datos.json). Si abriste el archivo ` +
        'directamente, sírvelo con <code>uv run rag servir</code>.</span></p>';
      return;
    }
    for (const p of estado.datos.preguntas) {
      p.normal = normalizar(p.texto);
      p.raices = raices(p.normal);
    }
    estado.datos.porId = new Map(estado.datos.preguntas.map((p) => [p.id, p]));
    pintarDocumentos();
    pintarSugerencias();
    actualizarEnviar();
    await revisarVivo();
    const url = new URLSearchParams(location.search);
    const version = url.get('v');
    if (version === 'v1' || version === 'v2') estado.version = version;
    const id = url.get('p');
    if (id && pregunta(id)) preguntar(pregunta(id).texto, { id });
  }

  iniciar();
})();
