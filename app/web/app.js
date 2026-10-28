// Sixth Official: match log. Replays one narrated match from its JSON file.
// One row per moment; the three viewers side by side. Every comment shown here was checked by
// the verifier before it "aired".
(() => {
'use strict';
const $ = (id) => document.getElementById(id);
const SVGNS = 'http://www.w3.org/2000/svg';
const S = { data: null, t: 0, playing: false, speed: 30, lang: 'en', shown: new Set(), last: 0, goalsSaid: new Set(),
            view: 'players', track: null, trackState: 'none', heatTeam: 'home', heatPlayer: '',
            shapeTeam: 'home', shapeState: 'out', shapeBlock: null,
            flip: true, deadShown: null };

// ---------------------------------------------------------------- words
const TXT = {
  en: {
    play: 'Play', pause: 'Pause', speed: 'Speed', realTime: '1x (real time)', nextGoal: 'Next goal', close: 'Close', scrub: 'Match time',
    win: 'Win chance', draw: 'Draw', checks: 'Fact checks', min: 'Min', moment: 'Moment',
    analyst: 'Analyst', fan: (c) => `${c} fan`, follow: (p) => p,
    checkLabels: ['passed first time', 'corrected on retry', 'replaced by template', 'drafts stopped'],
    status: { verified: 'Passed first time', verified_on_retry: 'Corrected on retry', fallback: 'Template' },
    noComment: 'No comment', empty: 'Nothing logged yet. Press Play.',
    caption: 'Match log: each moment, and what each viewer was told. Newest first.',
    goalSaid: (club, m) => `Goal, ${club}, ${m}`,
    viewPlay: 'Latest play', viewPlayers: 'All players', viewHeat: 'Heat map', viewShape: 'Shape', loading: 'Loading positions...',
    without: 'Without the ball', withBall: 'With the ball', phase: 'Phase of play', minutes: 'Minutes', setUp: 'Set up',
    blockName: (a, b) => `${a}' to ${b}'`, mOff: (m) => `${m} m off`,
    shapeWait: (club) => `${club}'s shape appears at 5': it is measured over minutes already played.`,
    shapeLive: 'Live: the last 15 minutes', liveTag: 'Live, ',
    shapeNone: 'Not enough play in this phase to judge (under a minute).',
    shapeCaption: (club, block, phase, best, m, next, nm, setup) => `${club}, ${block}, ${phase.toLowerCase()}: closest to ${best}, players on average ${m} m from their slots. Next closest: ${next} (${nm} m). Set up as ${setup}.`,
    shapeTypical: (setup, phase) => ` That is how a ${setup} usually looks ${phase.toLowerCase()}.`,
    shapeDrift: (setup, d) => ` Drift from a true ${setup}: ${d} m.`,
    shapeNote: 'Average positions over the block, measured from the team\'s centre so the shape shows, not where the ball was. Dots: players. Rings: the closest formation\'s slots. Lines: how far each player is from his slot.',
    why: { 'set-up': 'set-up', 'chasing the game': 'chasing the game', 'protecting a lead': 'protecting a lead' },
    changedTo: (f, m, why) => `changed to ${f} at ${m} (${why})`,
    team: 'Team', player: 'Player', wholeTeam: 'Whole team', less: 'Less', more: 'More ground covered',
    heatNote: (who, m) => `Where ${who} covered ground, from kick-off to ${m}. Each zone shows its share of the distance run. Darker means more.`,
    heatEmpty: 'Nothing to show before the first second of play.',
    heatAria: (who, m, zone, pct) => `Heat map: where ${who} covered ground up to ${m}. The most was in the ${zone}, ${pct}% of the distance.`,
    thirds: ['own third', 'middle third', 'final third'], channels: ['left', 'centre', 'right'],
    zoneName: (third, ch) => `${third}, ${ch}`,
    notePlay: 'The last 12 actions. Lines are passes, curves are crosses, dashes are runs with the ball, dotted lines are clearances, squares are restarts, small crosses are duels, dots are shots.',
    notePlayers: (club, d, n, dead) => (dead ? 'The ball is out of play, so there is no offside line until the restart. ' : `The solid line is the offside line: ${club}'s second-to-last defender (or the ball), ${d} m from their goal. ` +
      (n ? `Red rings: ${n} in an offside position. ` : '')) + 'Trails, last 4 seconds: pale is running (15 to 20 km/h), solid is high-speed (20 to 25 km/h), pink is a sprint (over 25 km/h). Squares are the officials: R referee, A assistants, 4 fourth official.',
    kits: 'Kit colors', reset: 'Reset', kitWarn: 'These two colors are hard to tell apart.',
    leadNote: 'The ringed and labelled player is the one in this moment; everyone else is dimmed. The fading lines are the actions that led to it. ',
    noTrack: 'Player positions are not available on this server.',
    goalOf: (c) => `${c} goal`,
    jump: (m) => `Show all players at ${m}`,
    playersAria: (m, club, d, n) => `All 22 players and the officials at ${m}. ${club} offside line ${d} m from their goal. ${n} attacker${n === 1 ? '' : 's'} in an offside position.`,
    zoom: { in: 'Zoom in', out: 'Zoom out', fit: 'Whole pitch', follow: 'Follow the ball' },
    hoverPlayer: (n, name, pos, club, kmh) => `${n} ${name}, ${pos}, ${club}. ${kmh} km/h. Click: his camera`,
    hoverOfficial: (role, kmh) => `${role}. ${kmh} km/h. Click: camera`,
    km: { label: 'Key moments', choose: 'Choose a moment to watch it', none: 'No key moments yet', again: 'Play it again',
      groups: { goal: 'Goals', penalty: 'Penalties', card: 'Cards', chance: 'Big chances', save: 'Saves', corner: 'Corners', through: 'Through balls' },
      caption: (m, what, who, xg) => `${what}, ${m}: ${who}.` + (xg ? ` xG ${xg}.` : '') },
    tbLabel: 'Through balls', tbChoose: 'Choose one to see the offside decision',
    tbOption: (m, a, b, o) => `${m} ${a} to ${b}: ${o}`, tbOutcome: { complete: 'completed', offside: 'offside', intercepted: 'cut out' },
    tbCaption: (m, from, to, margin, outcome) => `Through ball, ${m}: ${from} to ${to}. ` +
      (margin < -0.04 ? `Offside by ${(-margin).toFixed(1)} m` : margin < 0.05 ? 'Level, so onside' : `Onside by ${margin.toFixed(1)} m`) +
      ` at the pass. ${{ complete: 'Completed.', offside: 'Flagged by the assistant referee.', intercepted: 'Cut out by the defence.' }[outcome]}`,
    tbNone: 'No through balls in this match.',
    officials: 'Officials', allOfficials: 'All four officials', allWho: 'the four officials',
    officialWho: { ref: 'the referee', ar1: 'assistant referee 1', ar2: 'assistant referee 2', fourth: 'the fourth official' },
    officialName: { ref: 'Referee', ar1: 'Assistant referee 1', ar2: 'Assistant referee 2', fourth: 'Fourth official' },
    help: {
      title: 'How to use this page', link: 'How to use', close: 'Hide help',
      intro: 'A replay of one synthetic match, told as if live. Nothing after the current minute is shown: key moments, shapes and the match report appear as the match reaches them.',
      sections: [
        ['Watch the match', [
          'Press Play. Speed sets how fast the match runs: 1x is real time, 30x plays the whole match in 3 minutes.',
          'Drag the bar next to Speed to go to any minute. Next goal jumps to the next goal.',
          'Switch language with English / Español at the top right.']],
        ['The pitch', [
          'All players: every player, the four officials and the ball. A ball in the air shows its height. Trails show speed: pale is running, solid is high-speed, pink is a sprint.',
          'Latest play: the last 12 actions as a diagram (passes, crosses, runs with the ball, shots).',
          'Heat map: where a team, a player or an official covered ground. Shape: the formation each team is playing. Running: distance and speed zones for every player.',
          'Teams switch ends at half-time, as on TV. Untick the box to keep one direction. Kit colors change each club\'s color everywhere.']],
        ['Zoom, labels and cameras', [
          'Scroll over the pitch to zoom in or out where the pointer is. When zoomed, drag the pitch to move it. Whole pitch goes back.',
          'Point at a player for his name, number, position and speed. Click him to watch from his eyes in 3D.',
          'In the 3D camera, hold the middle mouse button (or the left button) and move the mouse to turn his head. Scroll to zoom. Look at the ball resets the view.']],
        ['Key moments', [
          'Goals, cards, big chances, saves, corners and through balls are listed as they happen, newest first.',
          'Pick one: the page goes back 8 seconds and replays the lead-up, then holds on the moment with the players involved ringed.',
          'Play it again repeats it. Player camera and Referee camera show the same moment in 3D.']],
        ['The numbers', [
          'Win chance: each club\'s chance to win, and the draw, right now. Click the chart, or use the arrow keys on it, to go to that minute.',
          'Last 10 minutes: territory, pressing and duels for each club. Each name links to the glossary.',
          'While the ball is out of play, a card shows what the restart could change, and whether anything unusual happened in the last 5 minutes.']],
        ['The commentary', [
          'Each row of the log is one moment, told three ways: for an analyst, a home fan and a fan who follows one player. An empty cell means that viewer was not told anything.',
          'Click a comment to see every fact behind it, where it came from, the tools the AI called and what the fact check stopped.',
          'Corrected on retry: the first draft failed a check and the AI fixed it. Template: it failed twice, so a plain sentence aired.']],
      ] },
    hints: {
      pitch: 'Scroll over the pitch to zoom. Point at a player for his name and speed; click him for his 3D camera.',
      km: 'Moments appear as the match reaches them. Pick one to replay the 8 seconds before it.',
      chart: 'Click the chart, or use the arrow keys on it, to go to that minute.',
      log: 'Each row is one moment, told three ways. Click a comment to see its facts, sources and fact check.' },
    gloss: 'Glossary: what each term means (xG, PPDA, duels, field tilt and more)',
    foot: 'Synthetic data only. Larkspur FC, Copper Vale and their players are fictional. Built for the Microsoft x Premier League Inside the Game hackathon.',
    ev: { goal: 'Goal', saved: 'Shot saved', blocked: 'Shot blocked', off_target: 'Shot off target', woodwork: 'Shot hits the woodwork', shot: 'Shot',
          save: 'Save', pass: 'Pass', passLost: 'Pass lost', carry: 'Run with the ball', carryLost: 'Run stopped', recovery: 'Ball won',
          pressure: 'Press', foul: 'Foul', yellow: 'Yellow card', red: 'Red card', offside: 'Offside',
          through: 'Through ball', throughLost: 'Through ball cut out', cross: 'Cross', crossLost: 'Cross cleared',
          duel: 'Duel won', aerial: 'Header won', tackle: 'Tackle', take_on: 'Beats his man', fifty_fifty: '50-50 won', clearance: 'Clearance',
          restart: { kick_off: 'Kick-off', throw_in: 'Throw-in', goal_kick: 'Goal kick', corner: 'Corner', free_kick: 'Free kick', penalty: 'Penalty' } },
    viewRunning: 'Running', flip: 'Teams switch ends at half-time',
    flatNote: ' Home always attacks to the right here.',
    dead: { out: 'Ball out of play', restartIn: (s) => `Restart in ${s} s`, kind: (k, c) => `${k}, ${c}`, direct: 'Free kick in shooting range',
      whatIf: 'If it goes in', setPiece: { corner: 'About 3 in 100 corners become goals.', free_kick: 'About 6 in 100 direct free kicks become goals.', penalty: 'About 78 in 100 penalties are scored.' },
      winNow: (c, a) => `${c} win chance now: ${a}%.`, winIf: (b) => `If it goes in: ${b}%.`,
      last5: 'Last 5 minutes against the match before',
      metric: { duels: (c) => `${c}: duels won`, passing: (c) => `${c}: passes completed`, territory: (c) => `${c}: share of final-third passes`, shots: (c) => `${c}: shots` },
      now: 'Last 5 min', before: 'Before', nowShort: 'Now', of: (k, n) => `${k} of ${n}`,
      shotsLine: (k, e) => `${k} in the last 5 minutes. At their earlier rate, about ${e} would be normal.`,
      unusual: (n) => `Unusual: a change this big happens by chance about 1 time in ${n}, allowing for the 8 things checked.`,
      normal: 'Within normal variation: a change this size often happens by chance.',
      none: 'Too early in the match to compare: findings start after 10 minutes.' },
    stats: { tilt: 'Field tilt', ppda: 'PPDA, lower is a harder press', duels: 'Duels won', xg: 'xG, whole match' },
    statsTitle: 'Last 10 minutes',
    chartTip: (m, c, a) => `${m} ${c} ${a}%`, chartAria: (m) => `Win chance chart, now at ${m}`,
    ft: { title: 'Full time', report: 'Match report', again: 'Watch again', toReport: 'Read the match report', ht: (h, a) => `Half-time ${h}, ${a}`, goals: 'Goals', none: 'No goals.',
      stats: 'Match stats', story: 'How it went', checks: 'Fact checks', copied: 'The real match',
      rows: { shots: 'Shots', sot: 'On target', xg: 'xG', passes: 'Passes', comp: 'Pass completion', duels: 'Duels won', corners: 'Corners', fouls: 'Fouls', yellow: 'Yellow cards', red: 'Red cards', offsides: 'Offsides' },
      pre: (H, h, d, A, a) => `Before kick-off: ${H} ${h}%, draw ${d}%, ${A} ${a}% (Elo ratings).`,
      result: { home: (c) => `${c} won.`, away: (c) => `${c} won.`, draw: () => 'The match was drawn.' },
      swing: (m, who, club, a, b) => `${m} goal by ${who}: ${club} win chance ${a}% to ${b}%.`,
      swingsTitle: 'The biggest swings', finding: (m, text) => `Most unusual moment, ${m}: ${text}`,
      checkLine: (n, ok, re, tm, st) => `${n} comments aired: ${ok} passed first time, ${re} corrected on retry, ${tm} replaced by a template. The verifier stopped ${st} drafts.`,
      copiedLine: (season, date) => `This match copies the box score of a real Premier League match: ${season}, ${date}. Goals in each half, shots, corners, fouls and cards are real; clubs, players and play are synthetic.`,
      rateText: { duels: (k, n, b) => `won ${k} of ${n} duels in 5 minutes, against ${b}% before`, passing: (k, n, b) => `completed ${k} of ${n} passes in 5 minutes, against ${b}% before`,
        territory: (k, n, b) => `made ${k} of ${n} final-third passes in 5 minutes, against ${b}% before`, shots: (k) => `took ${k} shots in 5 minutes` } },
    pre: (H, h, d, A, a) => `Before kick-off, from Elo ratings: ${H} ${h}%, draw ${d}%, ${A} ${a}%.`,
    history: (season, date) => `The box score copies a real Premier League match (${season}, ${date}): goals in each half, shots, corners, fouls and cards. Clubs and players are fictional.`,
    run: { player: 'Player', pos: 'Pos', dist: 'Total km', walk: 'Walk m', jog: 'Jog m', run: 'Run m', hsr: 'High-speed m', spr: 'Sprint m', n: 'Sprints', top: 'Top km/h', vs: 'Pace per 90 against the Premier League',
      typical: 'typical', high: 'high', low: 'low', keeper: 'no benchmark', off: 'sent off',
      note: (m) => `Running up to ${m}, from the 1 Hz positions. Speed zones as in FIFA's World Cup physical reports: walk 0 to 7 km/h, jog 7 to 15, run 15 to 20, high-speed 20 to 25, sprint over 25. Pace per 90 scales the total distance to a full match. Benchmark: Premier League means by position, 2019/20 and 2020/21.` },
    up: (z) => `${z} m up`,
  },
  es: {
    play: 'Reproducir', pause: 'Pausa', speed: 'Velocidad', realTime: '1x (tiempo real)', nextGoal: 'Siguiente gol', close: 'Cerrar', scrub: 'Tiempo de partido',
    win: 'Probabilidad de victoria', draw: 'Empate', checks: 'Comprobaciones', min: 'Min', moment: 'Momento',
    analyst: 'Analista', fan: (c) => `Afición de ${c}`, follow: (p) => p,
    checkLabels: ['correctos a la primera', 'corregidos al reintentar', 'sustituidos por plantilla', 'borradores parados'],
    status: { verified: 'Correcto a la primera', verified_on_retry: 'Corregido al reintentar', fallback: 'Plantilla' },
    noComment: 'Sin comentario', empty: 'Aún no hay nada. Pulse Reproducir.',
    caption: 'Registro del partido: cada momento y lo que se dijo a cada espectador. Lo más reciente primero.',
    goalSaid: (club, m) => `Gol, ${club}, ${m}`,
    viewPlay: 'Última jugada', viewPlayers: 'Todos los jugadores', viewHeat: 'Mapa de calor', viewShape: 'Forma', loading: 'Cargando posiciones...',
    without: 'Sin balón', withBall: 'Con balón', phase: 'Fase de juego', minutes: 'Minutos', setUp: 'Planteamiento',
    blockName: (a, b) => `del ${a}' al ${b}'`, mOff: (m) => `a ${m} m`,
    shapeWait: (club) => `La forma de ${club} aparece en el minuto 5: se mide sobre minutos ya jugados.`,
    shapeLive: 'En directo: los últimos 15 minutos', liveTag: 'En directo, ',
    shapeNone: 'No hay juego suficiente en esta fase para juzgar (menos de un minuto).',
    shapeCaption: (club, block, phase, best, m, next, nm, setup) => `${club}, ${block}, ${phase.toLowerCase()}: lo más cercano es un ${best}, con los jugadores a ${m} m de media de su sitio. Después: ${next} (${nm} m). Planteamiento: ${setup}.`,
    shapeTypical: (setup, phase) => ` Así suele verse un ${setup} ${phase.toLowerCase()}.`,
    shapeDrift: (setup, d) => ` Desvío respecto a un ${setup} puro: ${d} m.`,
    shapeNote: 'Posiciones medias del bloque, medidas desde el centro del equipo para que se vea la forma y no dónde estaba el balón. Puntos: jugadores. Aros: los sitios de la formación más cercana. Líneas: la distancia de cada jugador a su sitio.',
    why: { 'set-up': 'planteamiento', 'chasing the game': 'buscando el partido', 'protecting a lead': 'protegiendo la ventaja' },
    changedTo: (f, m, why) => `cambia a ${f} en el ${m} (${why})`,
    team: 'Equipo', player: 'Jugador', wholeTeam: 'Todo el equipo', less: 'Menos', more: 'Más distancia recorrida',
    heatNote: (who, m) => `Dónde recorrió distancia ${who}, desde el inicio hasta el ${m}. Cada zona muestra su parte de la distancia. Más oscuro es más.`,
    heatEmpty: 'Nada que mostrar antes del primer segundo de juego.',
    heatAria: (who, m, zone, pct) => `Mapa de calor: dónde recorrió distancia ${who} hasta el ${m}. Lo máximo fue en ${zone}, el ${pct}% de la distancia.`,
    thirds: ['tercio propio', 'tercio central', 'último tercio'], channels: ['izquierda', 'centro', 'derecha'],
    zoneName: (third, ch) => `${third}, ${ch}`,
    notePlay: 'Las últimas 12 acciones. Líneas: pases; curvas: centros; trazos: conducciones; punteado: despejes; cuadrados: reanudaciones; aspas: duelos; puntos: disparos.',
    notePlayers: (club, d, n, dead) => (dead ? 'El balón está fuera, así que no hay línea de fuera de juego hasta la reanudación. ' : `La línea continua es la del fuera de juego: el penúltimo defensor de ${club} (o el balón), a ${d} m de su portería. ` +
      (n ? `Aros rojos: ${n} en posición de fuera de juego. ` : '')) + 'Estelas, últimos 4 segundos: clara es carrera (15 a 20 km/h), sólida es alta velocidad (20 a 25 km/h), rosa es un sprint (más de 25 km/h). Los cuadrados son los árbitros: R principal, A asistentes, 4 cuarto árbitro.',
    kits: 'Colores de los equipos', reset: 'Restablecer', kitWarn: 'Estos dos colores se distinguen mal.',
    leadNote: 'El jugador con aro y etiqueta es el de este momento; los demás aparecen atenuados. Las líneas que se desvanecen son las acciones que llevaron a él. ',
    noTrack: 'Las posiciones de los jugadores no están disponibles en este servidor.',
    goalOf: (c) => `Portería de ${c}`,
    jump: (m) => `Ver todos los jugadores en el ${m}`,
    playersAria: (m, club, d, n) => `Los 22 jugadores y los árbitros en el ${m}. Línea de fuera de juego de ${club} a ${d} m de su portería. ${n} atacante${n === 1 ? '' : 's'} en posición de fuera de juego.`,
    zoom: { in: 'Acercar', out: 'Alejar', fit: 'Campo entero', follow: 'Seguir el balón' },
    hoverPlayer: (n, name, pos, club, kmh) => `${n} ${name}, ${pos}, ${club}. ${kmh} km/h. Clic: su cámara`,
    hoverOfficial: (role, kmh) => `${role}. ${kmh} km/h. Clic: cámara`,
    km: { label: 'Momentos clave', choose: 'Elija un momento para verlo', none: 'Aún no hay momentos clave', again: 'Verlo otra vez',
      groups: { goal: 'Goles', penalty: 'Penaltis', card: 'Tarjetas', chance: 'Ocasiones claras', save: 'Paradas', corner: 'Córners', through: 'Pases al hueco' },
      caption: (m, what, who, xg) => `${what}, ${m}: ${who}.` + (xg ? ` xG ${xg}.` : '') },
    tbLabel: 'Pases al hueco', tbChoose: 'Elija uno para ver la decisión de fuera de juego',
    tbOption: (m, a, b, o) => `${m} de ${a} a ${b}: ${o}`, tbOutcome: { complete: 'completado', offside: 'fuera de juego', intercepted: 'cortado' },
    tbCaption: (m, from, to, margin, outcome) => `Pase al hueco, ${m}: de ${from} a ${to}. ` +
      (margin < -0.04 ? `Fuera de juego por ${(-margin).toFixed(1).replace('.', ',')} m` : margin < 0.05 ? 'En línea, así que habilitado' : `Habilitado por ${margin.toFixed(1).replace('.', ',')} m`) +
      ` en el pase. ${{ complete: 'Completado.', offside: 'Señalado por el árbitro asistente.', intercepted: 'Cortado por la defensa.' }[outcome]}`,
    tbNone: 'No hay pases al hueco en este partido.',
    officials: 'Árbitros', allOfficials: 'Los cuatro árbitros', allWho: 'los cuatro árbitros',
    officialWho: { ref: 'el árbitro', ar1: 'el árbitro asistente 1', ar2: 'el árbitro asistente 2', fourth: 'el cuarto árbitro' },
    officialName: { ref: 'Árbitro', ar1: 'Árbitro asistente 1', ar2: 'Árbitro asistente 2', fourth: 'Cuarto árbitro' },
    help: {
      title: 'Cómo usar esta página', link: 'Cómo usarla', close: 'Ocultar ayuda',
      intro: 'La repetición de un partido sintético, contada como si fuera en directo. No se muestra nada posterior al minuto actual: los momentos clave, las formas y el informe aparecen cuando el partido llega a ellos.',
      sections: [
        ['Ver el partido', [
          'Pulse Reproducir. La velocidad fija cuánto corre el partido: 1x es tiempo real, 30x juega el partido entero en 3 minutos.',
          'Arrastre la barra junto a Velocidad para ir a cualquier minuto. Siguiente gol salta al próximo gol.',
          'Cambie de idioma con English / Español, arriba a la derecha.']],
        ['El campo', [
          'Todos los jugadores: cada jugador, los cuatro árbitros y el balón. Un balón en el aire muestra su altura. Las estelas muestran la velocidad: pálida es carrera, sólida es alta velocidad, rosa es un sprint.',
          'Última jugada: las 12 últimas acciones en un diagrama (pases, centros, conducciones, disparos).',
          'Mapa de calor: dónde cubrió terreno un equipo, un jugador o un árbitro. Forma: la formación de cada equipo. Carrera: distancia y zonas de velocidad de cada jugador.',
          'Los equipos cambian de campo en el descanso, como en la televisión. Desmarque la casilla para mantener una dirección. Colores de equipación cambia el color de cada club en toda la página.']],
        ['Zoom, etiquetas y cámaras', [
          'Use la rueda sobre el campo para acercar o alejar donde está el puntero. Con zoom, arrastre el campo para moverlo. Campo entero vuelve atrás.',
          'Apunte a un jugador para ver su nombre, dorsal, posición y velocidad. Haga clic para verlo desde sus ojos en 3D.',
          'En la cámara 3D, mantenga el botón central del ratón (o el izquierdo) y mueva el ratón para girar la cabeza. La rueda acerca la vista. Mirar al balón la restablece.']],
        ['Momentos clave', [
          'Goles, tarjetas, ocasiones claras, paradas, córners y pases al hueco aparecen según ocurren, del más reciente al más antiguo.',
          'Elija uno: la página vuelve 8 segundos atrás, repite la jugada previa y se detiene en el momento, con los jugadores implicados marcados.',
          'Verlo otra vez lo repite. Cámara del jugador y Cámara del árbitro muestran el mismo momento en 3D.']],
        ['Los números', [
          'Probabilidad de victoria: la de cada club, y la del empate, en este momento. Haga clic en el gráfico, o use las flechas sobre él, para ir a ese minuto.',
          'Últimos 10 minutos: territorio, presión y duelos de cada club. Cada nombre enlaza con el glosario.',
          'Con el balón fuera de juego, una tarjeta muestra qué puede cambiar la reanudación y si pasó algo inusual en los últimos 5 minutos.']],
        ['Los comentarios', [
          'Cada fila del registro es un momento contado de tres maneras: para un analista, un aficionado local y un seguidor de un jugador. Una celda vacía significa que a ese espectador no se le dijo nada.',
          'Haga clic en un comentario para ver cada dato, de dónde salió, las herramientas que llamó la IA y lo que paró la comprobación.',
          'Corregido al reintentar: el primer borrador falló una comprobación y la IA lo arregló. Plantilla: falló dos veces y salió una frase simple.']],
      ] },
    hints: {
      pitch: 'Use la rueda sobre el campo para acercar. Apunte a un jugador para ver su nombre y velocidad; haga clic para su cámara 3D.',
      km: 'Los momentos aparecen cuando el partido llega a ellos. Elija uno para repetir los 8 segundos previos.',
      chart: 'Haga clic en el gráfico, o use las flechas sobre él, para ir a ese minuto.',
      log: 'Cada fila es un momento contado de tres maneras. Haga clic en un comentario para ver sus datos, fuentes y comprobación.' },
    gloss: 'Glosario: qué significa cada término (xG, PPDA, duelos, dominio territorial y más; en inglés)',
    foot: 'Solo datos sintéticos. Larkspur FC, Copper Vale y sus jugadores son ficticios. Hecho para el hackathon Inside the Game de Microsoft y la Premier League.',
    ev: { goal: 'Gol', saved: 'Disparo parado', blocked: 'Disparo bloqueado', off_target: 'Disparo fuera', woodwork: 'Disparo al palo', shot: 'Disparo',
          save: 'Parada', pass: 'Pase', passLost: 'Pase perdido', carry: 'Conducción', carryLost: 'Conducción cortada', recovery: 'Balón recuperado',
          pressure: 'Presión', foul: 'Falta', yellow: 'Tarjeta amarilla', red: 'Tarjeta roja', offside: 'Fuera de juego',
          through: 'Pase al hueco', throughLost: 'Pase al hueco cortado', cross: 'Centro', crossLost: 'Centro despejado',
          duel: 'Duelo ganado', aerial: 'Duelo aéreo ganado', tackle: 'Entrada', take_on: 'Regate', fifty_fifty: 'Balón dividido ganado', clearance: 'Despeje',
          restart: { kick_off: 'Saque inicial', throw_in: 'Saque de banda', goal_kick: 'Saque de puerta', corner: 'Córner', free_kick: 'Falta', penalty: 'Penalti' } },
    viewRunning: 'Carrera', flip: 'Los equipos cambian de campo en el descanso',
    flatNote: ' Aquí el local siempre ataca hacia la derecha.',
    dead: { out: 'Balón fuera', restartIn: (s) => `Se reanuda en ${s} s`, kind: (k, c) => `${k}, ${c}`, direct: 'Falta en zona de disparo',
      whatIf: 'Si entra', setPiece: { corner: 'Unos 3 de cada 100 córners acaban en gol.', free_kick: 'Unas 6 de cada 100 faltas directas acaban en gol.', penalty: 'Se marcan unos 78 de cada 100 penaltis.' },
      winNow: (c, a) => `Probabilidad de victoria de ${c} ahora: ${a}%.`, winIf: (b) => `Si entra: ${b}%.`,
      last5: 'Últimos 5 minutos frente al resto del partido',
      metric: { duels: (c) => `${c}: duelos ganados`, passing: (c) => `${c}: pases completados`, territory: (c) => `${c}: parte de los pases en el último tercio`, shots: (c) => `${c}: disparos` },
      now: 'Últimos 5 min', before: 'Antes', nowShort: 'Ahora', of: (k, n) => `${k} de ${n}`,
      shotsLine: (k, e) => `${k} en los últimos 5 minutos. A su ritmo anterior, lo normal serían unos ${e}.`,
      unusual: (n) => `Inusual: un cambio así ocurre por azar 1 vez de cada ${n}, contando las 8 cosas comprobadas.`,
      normal: 'Variación normal: un cambio así ocurre a menudo por azar.',
      none: 'Demasiado pronto para comparar: los datos empiezan a los 10 minutos.' },
    stats: { tilt: 'Dominio territorial', ppda: 'PPDA, menos es más presión', duels: 'Duelos ganados', xg: 'xG, todo el partido' },
    statsTitle: 'Últimos 10 minutos',
    chartTip: (m, c, a) => `${m} ${c} ${a}%`, chartAria: (m) => `Gráfico de probabilidad de victoria, ahora en el ${m}`,
    ft: { title: 'Final del partido', report: 'Crónica del partido', again: 'Ver otra vez', toReport: 'Leer la crónica', ht: (h, a) => `Descanso ${h}, ${a}`, goals: 'Goles', none: 'Sin goles.',
      stats: 'Estadísticas', story: 'Cómo fue', checks: 'Comprobaciones', copied: 'El partido real',
      rows: { shots: 'Disparos', sot: 'A puerta', xg: 'xG', passes: 'Pases', comp: 'Acierto en el pase', duels: 'Duelos ganados', corners: 'Córners', fouls: 'Faltas', yellow: 'Amarillas', red: 'Rojas', offsides: 'Fueras de juego' },
      pre: (H, h, d, A, a) => `Antes del partido: ${H} ${h}%, empate ${d}%, ${A} ${a}% (Elo).`,
      result: { home: (c) => `Ganó ${c}.`, away: (c) => `Ganó ${c}.`, draw: () => 'El partido terminó en empate.' },
      swing: (m, who, club, a, b) => `Gol de ${who} en el ${m}: probabilidad de victoria de ${club} del ${a}% al ${b}%.`,
      swingsTitle: 'Los mayores vuelcos', finding: (m, text) => `Momento más inusual, ${m}: ${text}`,
      checkLine: (n, ok, re, tm, st) => `${n} comentarios emitidos: ${ok} correctos a la primera, ${re} corregidos al reintentar, ${tm} sustituidos por plantilla. El verificador paró ${st} borradores.`,
      copiedLine: (season, date) => `Este partido copia las estadísticas de un partido real de la Premier League: ${season}, ${date}. Goles por parte, disparos, córners, faltas y tarjetas son reales; clubes, jugadores y juego son sintéticos.`,
      rateText: { duels: (k, n, b) => `ganó ${k} de ${n} duelos en 5 minutos, frente al ${b}% de antes`, passing: (k, n, b) => `completó ${k} de ${n} pases en 5 minutos, frente al ${b}% de antes`,
        territory: (k, n, b) => `hizo ${k} de ${n} pases en el último tercio en 5 minutos, frente al ${b}% de antes`, shots: (k) => `disparó ${k} veces en 5 minutos` } },
    pre: (H, h, d, A, a) => `Antes del partido, según el Elo: ${H} ${h}%, empate ${d}%, ${A} ${a}%.`,
    history: (season, date) => `Las estadísticas copian un partido real de la Premier League (${season}, ${date}): goles por parte, disparos, córners, faltas y tarjetas. Clubes y jugadores son ficticios.`,
    run: { player: 'Jugador', pos: 'Pos', dist: 'Total km', walk: 'Andar m', jog: 'Trote m', run: 'Carrera m', hsr: 'Alta velocidad m', spr: 'Sprint m', n: 'Sprints', top: 'Máx. km/h', vs: 'Ritmo por 90 frente a la Premier League',
      typical: 'normal', high: 'alto', low: 'bajo', keeper: 'sin referencia', off: 'expulsado',
      note: (m) => `Carrera hasta el ${m}, a partir de las posiciones a 1 Hz. Zonas de velocidad como en los informes físicos del Mundial de la FIFA: andar 0 a 7 km/h, trote 7 a 15, carrera 15 a 20, alta velocidad 20 a 25, sprint más de 25. El ritmo por 90 lleva la distancia total a un partido completo. Referencia: medias de la Premier League por puesto, 2019/20 y 2020/21.` },
    up: (z) => `a ${z} m del suelo`,
  },
};
const minute = (t) => Math.min(90, Math.floor(t / 60) + 1);
const num1 = (v) => (S.lang === 'es' ? v.toFixed(1).replace('.', ',') : v.toFixed(1));   // Spanish decimal comma
const num2 = (v) => (S.lang === 'es' ? v.toFixed(2).replace('.', ',') : v.toFixed(2));
const minLabel = (t) => (t >= 5400 ? "90'" : `${minute(t)}'`);
// Ends: the data always has the home club attacking toward x = 105. With the half-time switch on,
// the live views (Latest play, All players, Running) turn the pitch round for the second half, as
// the clubs do. Heat map and Shape add up the whole match, so they keep one direction.
const runKey = { k: '' };
const flipped = (t) => S.flip && t >= 2700;
const MX = (x, t) => (flipped(t) ? 105 - x : x);
const MY = (y, t) => (flipped(t) ? 68 - y : y);

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
function sv(tag, attrs) { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v); return e; }

// ---------------------------------------------------------------- data
async function load() {
  const q = new URLSearchParams(location.search).get('match');
  let file = q ? `data/${q}` : null;
  if (!file) {
    try { const r = await fetch('api/matches'); const list = await r.json(); file = list.length ? `data/${list[0]}` : null; } catch (e) { /* static hosting */ }
  }
  const r = await fetch(file || 'data/match.json');
  if (!r.ok) throw new Error(`could not load ${file}`);
  const d = await r.json();
  // One moment per event id. Each persona has at most one comment per moment, in one or two languages.
  const moments = new Map();
  for (const c of d.comments) {
    const o = c.output;
    if (!moments.has(o.event_id)) moments.set(o.event_id, { id: o.event_id, at: o.match_clock_s, goal: !!c.is_goal, by: {} });
    const m = moments.get(o.event_id);
    const slot = m.by[o.user_id] || (m.by[o.user_id] = { air: c.air_s ?? o.match_clock_s, at: o.match_clock_s, langs: {} });
    slot.langs[o.language] = c;
    m.goal = m.goal || !!c.is_goal;
  }
  for (const m of moments.values()) m.first = Math.min(...Object.values(m.by).map((s) => s.air));
  d.moments = [...moments.values()].sort((a, b) => a.at - b.at);
  d.cards = Object.fromEntries(d.timeline.notable.filter((n) => n.type === 'foul').map((n) => [n.event_id, n.outcome]));
  d.deadball = (d.deadball || []).slice().sort((a, b) => a.t0 - b.t0);
  return d;
}
const pick = (slot) => slot.langs[S.lang] || Object.values(slot.langs)[0];
// A player's name with his shirt number and team-sheet position: "Nico Halvorsen (9, LS)".
function who(name) {
  const sheet = S.data && S.data.lineup ? Object.values(S.data.lineup).find((p) => p.name === name) : null;
  return sheet ? `${name} (${sheet.number}, ${sheet.position})` : name;
}

// What happened at a moment, from the compact event list: [t, type, team, x, y, ex, ey, outcome, player].
function describe(id) {
  const D = S.data, E = TXT[S.lang].ev;
  const ev = D.timeline.events[parseInt(id.slice(1), 10) - 1];
  if (!ev) return { what: id, who: '', team: null };
  const type = D.timeline.event_types[ev[1]], out = ev[7], team = ev[2] === 0 ? 'home' : 'away';
  let what = E[type] || type;
  if (type === 'shot') what = E[out] || E.shot;
  if (type === 'pass' && out === 'failure') what = E.passLost;
  if (type === 'pass' && ev[9] === 'through') what = out === 'failure' ? E.throughLost : E.through;
  if (type === 'pass' && ev[9] === 'cross') what = out === 'failure' ? E.crossLost : E.cross;
  if (type === 'carry' && out === 'failure') what = E.carryLost;
  if (type === 'foul' && D.cards[id]) what = E[D.cards[id]] || E.foul;
  if (type === 'duel') what = E[ev[11]] || E.duel;
  if (type === 'restart') what = E.restart[ev[10]] || type;
  return { what, who: `${who(ev[8])}, ${D.clubs[team]}`, team };
}

// ---------------------------------------------------------------- scoreboard, win chance, checks
function stateAt(t) {
  const s = S.data.timeline.series; let lo = 0, hi = s.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (s[m][0] <= t) lo = m; else hi = m - 1; }
  return s[lo];
}
function airedSlots() {
  const out = [];
  for (const m of S.data.moments) for (const s of Object.values(m.by)) if (s.air <= S.t) out.push(pick(s));
  return out;
}
function drawBoard() {
  let r = stateAt(S.t);
  const T = TXT[S.lang];
  if (S.t >= 5400 - 0.5) {                    // full time: the result is settled
    const [h, a] = [r[4], r[5]];
    r = r.slice(); r[1] = h > a ? 1 : 0; r[2] = h === a ? 1 : 0;
  }
  $('home-goals').textContent = r[4]; $('away-goals').textContent = r[5]; $('clock').textContent = minLabel(S.t);
  $('scrub').value = Math.round(S.t);
  const h = Math.round(r[1] * 100), d = Math.round(r[2] * 100), a = Math.max(0, 100 - h - d);
  const wkey = `${h}|${d}|${S.lang}`;
  if (wkey !== drawBoard.wkey) {
    drawBoard.wkey = wkey;
    $('win').replaceChildren(
      el('div', { class: 'home' }, el('dt', {}, S.data.clubs.home), el('dd', {}, `${h}%`)),
      el('div', { class: 'draw' }, el('dt', {}, T.draw), el('dd', {}, `${d}%`)),
      el('div', { class: 'away' }, el('dt', {}, S.data.clubs.away), el('dd', {}, `${a}%`)));
    const [bh, bd, ba] = $('winbar').children;
    bh.style.width = `${h}%`; bd.style.width = `${d}%`; ba.style.width = `${a}%`;
  }
  const aired = airedSlots();
  const st = (k) => aired.filter((c) => c.output.status === k).length;
  const stopped = aired.reduce((n, c) => n + c.tries.filter((x) => !x.passed).length, 0);
  const vals = [st('verified'), st('verified_on_retry'), st('fallback'), stopped];
  const ckey = vals.join('|') + S.lang;
  if (ckey !== drawBoard.ckey) {
    drawBoard.ckey = ckey;
    const cls = ['ok', 'retry', 'tmpl', 'stop'];
    $('checks').replaceChildren(...vals.map((v, i) => el('div', { class: cls[i] }, el('dt', {}, T.checkLabels[i]), el('dd', {}, String(v)))));
  }
  // Disabled state: no goal left after this minute.
  $('next-goal').disabled = !S.data.timeline.notable.some((x) => x.goal && x.t > S.t + 1);
}

// ---------------------------------------------------------------- chart: win chance over time, the future faded
let chart = null;
function buildChart() {
  const svg = $('chart'); svg.replaceChildren();
  const W = 1000, H = 84; svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const x = (t) => (t / 5400) * W, y = (p) => H - p * H;
  const s = S.data.timeline.series;
  const pts = (f) => s.map((r) => `${x(r[0]).toFixed(1)},${y(f(r)).toFixed(1)}`).join(' ');
  const back = (f) => s.slice().reverse().map((r) => `${x(r[0]).toFixed(1)},${y(f(r)).toFixed(1)}`).join(' ');
  const area = (lo, hi, cls) => svg.append(sv('polygon', { points: pts(hi) + ' ' + back(lo), fill: `var(--${cls})` }));
  area(() => 0, (r) => r[1], 'home');
  area((r) => r[1], (r) => r[1] + r[2], 'draw');
  area((r) => r[1] + r[2], () => 1, 'away');
  svg.append(sv('line', { x1: x(2700), y1: 0, x2: x(2700), y2: H, stroke: 'var(--paper)', 'stroke-width': 2 }));
  for (const n of S.data.timeline.notable) if (n.goal) svg.append(sv('line', { x1: x(n.t), y1: 0, x2: x(n.t), y2: H, stroke: 'var(--ink)', 'stroke-width': 2 }));
  const future = sv('rect', { x: 0, y: 0, width: W, height: H, fill: 'var(--paper)', opacity: 0.7 });
  const head = sv('line', { x1: 0, y1: 0, x2: 0, y2: H, stroke: 'var(--ink)', 'stroke-width': 3 });
  svg.append(future, head);
  chart = { future, head, x, W };
}
// The chart is a control: click a point (or use the arrow keys) to go to that minute. Hovering
// shows the minute and the home club's win chance there.
function chartTime(e) {
  const r = $('chart').getBoundingClientRect();
  return Math.max(0, Math.min(5400, ((e.clientX - r.left) / r.width) * 5400));
}
function chartTip(t, px) {
  const tip = $('chart-tip'), r = stateAt(t), T = TXT[S.lang];
  tip.textContent = T.chartTip(minLabel(t), S.data.clubs.home, Math.round(r[1] * 100));
  tip.style.left = `${px}px`; tip.hidden = false;
}
$('chart').addEventListener('mousemove', (e) => { if (S.data) chartTip(chartTime(e), e.clientX - $('chart').getBoundingClientRect().left); });
$('chart').addEventListener('mouseleave', () => { $('chart-tip').hidden = true; });
$('chart').addEventListener('click', (e) => { if (S.data) { S.t = chartTime(e); S.freeze = null; } });
$('chart').addEventListener('keydown', (e) => {
  if (!S.data) return;
  const step = { ArrowLeft: -60, ArrowRight: 60, PageDown: -600, PageUp: 600, Home: -1e9, End: 1e9 }[e.key];
  if (step == null) return;
  e.preventDefault(); S.t = Math.max(0, Math.min(5400, S.t + step));
});
function drawChart() {
  const px = chart.x(S.t);
  chart.future.setAttribute('x', px); chart.future.setAttribute('width', Math.max(0, chart.W - px));
  chart.head.setAttribute('x1', px); chart.head.setAttribute('x2', px);
  const m = minute(S.t);
  if (m !== drawChart.m) { drawChart.m = m; $('chart').setAttribute('aria-valuenow', String(m)); $('chart').setAttribute('aria-valuetext', TXT[S.lang].chartAria(minLabel(S.t))); }
}

// ---------------------------------------------------------------- pitch: the latest play, drawn like a diagram
let pitchLayer = null, playersLayer = null, heatLayer = null, goalLabels = null, shapeLayer = null;
// The pitch is split into 18 zones: 6 along its length (so each third is two zones) and
// 3 across it (left, centre, right channels). The heat map fills these zones.
const ZONE_W = 105 / 6, ZONE_H = 68 / 3;
function buildPitch() {
  const svg = $('pitch'); svg.replaceChildren();
  // Mowing stripes, as on a broadcast pitch: 12 flat bands, alternate ones a shade lighter.
  const stripes = sv('g', { fill: 'var(--pitch-2)' });
  for (let k = 1; k < 12; k += 2) stripes.append(sv('rect', { x: k * 105 / 12, y: 0, width: 105 / 12, height: 68 }));
  svg.append(stripes);
  heatLayer = { g: sv('g', {}), tg: sv('g', {}), cells: [], key: '' }; svg.append(heatLayer.g);   // colors under the lines
  shapeLayer = { g: sv('g', {}), key: '' };
  const grid = sv('g', { stroke: 'var(--pitch-line)', 'stroke-width': 0.18, 'stroke-dasharray': '0.7 0.9', opacity: 0.6 });
  for (let c = 1; c < 6; c++) if (c !== 3) grid.append(sv('line', { x1: c * ZONE_W, y1: 0, x2: c * ZONE_W, y2: 68 }));
  for (let r = 1; r < 3; r++) grid.append(sv('line', { x1: 0, y1: r * ZONE_H, x2: 105, y2: r * ZONE_H }));
  svg.append(grid);
  const g = sv('g', { fill: 'none', stroke: 'var(--pitch-line)', 'stroke-width': 0.35 });
  g.append(sv('rect', { x: 0, y: 0, width: 105, height: 68 }), sv('line', { x1: 52.5, y1: 0, x2: 52.5, y2: 68 }),
           sv('circle', { cx: 52.5, cy: 34, r: 9.15 }), sv('rect', { x: 0, y: 13.84, width: 16.5, height: 40.32 }),
           sv('rect', { x: 88.5, y: 13.84, width: 16.5, height: 40.32 }), sv('rect', { x: 0, y: 24.84, width: 5.5, height: 18.32 }),
           sv('rect', { x: 99.5, y: 24.84, width: 5.5, height: 18.32 }), sv('rect', { x: -1.5, y: 30.34, width: 1.5, height: 7.32 }),
           sv('rect', { x: 105, y: 30.34, width: 1.5, height: 7.32 }));
  svg.append(g);
  goalLabels = sv('g', {}); svg.append(goalLabels);
  const lab = (x, a) => { const e = sv('text', { x, y: 66.4, fill: 'var(--muted)', 'font-size': 2.2, 'text-anchor': a, 'font-family': 'var(--ui)' }); goalLabels.append(e); return e; };
  // Home attacks toward x = 105, so the left goal is the home club's (until the teams switch ends).
  goalLabels.left = lab(1.5, 'start'); goalLabels.right = lab(103.5, 'end'); goalLabels.key = '';
  svg.append(heatLayer.tg);                          // numbers above the lines
  svg.append(shapeLayer.g);
  pitchLayer = sv('g', {}); svg.append(pitchLayer);
  playersLayer = null;
  if (S.trackState === 'ready') { buildPlayers(); buildHeat(); }
}
function lastEventIndex(t) {
  const ev = S.data.timeline.events; let lo = -1, hi = ev.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (ev[m][0] <= t) lo = m; else hi = m - 1; }
  return lo;
}
function drawGoalLabels(flat) {
  const f = !flat && flipped(S.t), key = `${f}|${S.lang}`;
  if (key === goalLabels.key) return;
  goalLabels.key = key;
  const T = TXT[S.lang], [l, r] = f ? ['away', 'home'] : ['home', 'away'];
  goalLabels.left.textContent = T.goalOf(S.data.clubs[l]); goalLabels.right.textContent = T.goalOf(S.data.clubs[r]);
}
function drawPitch() {
  const ready = S.trackState === 'ready', showPlayers = (S.view === 'players' || S.view === 'running') && ready, showHeat = S.view === 'heat' && ready;
  drawGoalLabels(S.view === 'heat' || S.view === 'shape');
  const showShape = S.view === 'shape' && ready;
  shapeLayer.g.style.display = showShape ? '' : 'none';
  if (showShape) {
    pitchLayer.style.display = 'none'; heatLayer.g.style.display = heatLayer.tg.style.display = 'none';
    if (playersLayer) playersLayer.g.style.display = 'none';
    goalLabels.style.display = ''; drawShape(); return;
  }
  pitchLayer.style.display = showPlayers || showHeat ? 'none' : '';
  if (playersLayer) playersLayer.g.style.display = showPlayers ? '' : 'none';
  heatLayer.g.style.display = heatLayer.tg.style.display = showHeat ? '' : 'none';
  goalLabels.style.display = showHeat ? 'none' : '';      // the labels would sit on dark zones
  if (showPlayers) { drawPlayers(); if (S.view === 'running') drawRunning(); return; }
  if (showHeat) { drawHeat(); return; }
  drawActions(pitchLayer, lastEventIndex(S.t), 12, true);
}
// The last n actions up to event i, drawn as a diagram: lines, curves, squares, dots. Also used on
// top of All players when a key moment is picked, so the lead-up shows with every player.
function drawActions(layer, i, n, withBall) {
  const ev = S.data.timeline.events, types = S.data.timeline.event_types, pitchLayer = layer;
  pitchLayer.replaceChildren();
  for (let k = Math.max(0, i - (n - 1)); k <= i; k++) {
    const r = ev[k], [et, ty, team] = r, type = types[ty], out = r[7];
    const x = MX(r[3], et), y = MY(r[4], et), ex = r[5] == null ? null : MX(r[5], et), ey = r[6] == null ? null : MY(r[6], et);
    const op = (1 - (i - k) / n) * 0.95, col = team === 0 ? 'var(--home)' : 'var(--away)';
    if (type === 'pressure') continue;                     // pressure shows on the pass it came with
    if (ex != null && type === 'pass' && ev[k][9] === 'cross') {
      // A cross: a curve bowed away from the touchline it came from, ending in a ring.
      const mx = (x + ex) / 2, my = (y + ey) / 2, dx = ex - x, dy = ey - y, len = Math.hypot(dx, dy) || 1;
      const nx = -dy / len, ny = dx / len, bow = Math.min(8, len * 0.3);
      const side = Math.sign(ny * (my - 34)) || 1;           // bow away from the middle of the pitch
      const cx = mx + nx * bow * side, cy = my + ny * bow * side;
      pitchLayer.append(sv('path', { d: `M${x},${y} Q${cx},${cy} ${ex},${ey}`, fill: 'none', stroke: col, 'stroke-width': 0.8, opacity: op, 'stroke-linecap': 'round' }));
      pitchLayer.append(sv('circle', { cx: ex, cy: ey, r: 1.1, fill: 'none', stroke: col, 'stroke-width': 0.45, opacity: op }));
    } else if (ex != null) pitchLayer.append(sv('line', { x1: x, y1: y, x2: ex, y2: ey, stroke: col, 'stroke-width': type === 'carry' ? 0.9 : 0.55, opacity: op, 'stroke-dasharray': type === 'carry' ? '1 0.8' : (type === 'clearance' ? '0.4 0.6' : null), 'stroke-linecap': 'round' }));
    if (type === 'restart') pitchLayer.append(sv('rect', { x: x - 1, y: y - 1, width: 2, height: 2, fill: 'none', stroke: col, 'stroke-width': 0.45, opacity: op }));
    if (type === 'duel') pitchLayer.append(sv('path', { d: `M${x - 0.9},${y - 0.9} L${x + 0.9},${y + 0.9} M${x - 0.9},${y + 0.9} L${x + 0.9},${y - 0.9}`, stroke: col, 'stroke-width': 0.45, opacity: op }));
    if (type === 'shot') {
      pitchLayer.append(sv('circle', { cx: x, cy: y, r: 1.4, fill: col, opacity: op }));
      if (out === 'goal' && withBall) pitchLayer.append(sv('circle', { cx: x, cy: y, r: 3.2, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 0.5, opacity: op }));
    } else if (['recovery', 'foul', 'pressure', 'offside', 'save'].includes(type)) {
      pitchLayer.append(sv('rect', { x: x - 0.7, y: y - 0.7, width: 1.4, height: 1.4, fill: col, opacity: op * 0.8 }));
    }
  }
  if (withBall && i >= 0) { const r = ev[i]; pitchLayer.append(sv('circle', { cx: MX(r[5] ?? r[3], r[0]), cy: MY(r[6] ?? r[4], r[0]), r: 1.0, fill: 'var(--ink)' })); }
}

// ---------------------------------------------------------------- pitch: all 22 players at this moment
// Positions come from /api/tracking (1 Hz, modelled by the generator) and are blended between seconds.
async function loadTracking() {
  if (S.trackState === 'ready' || S.trackState === 'loading') return;
  S.trackState = 'loading'; viewButtons();
  try {
    const r = await fetch(`api/tracking?seed=${S.data.seed}`);
    if (!r.ok) throw new Error(r.status);
    S.track = await r.json(); S.motion = window.makeMotion ? window.makeMotion(S.track) : null;
    S.trackState = 'ready'; buildPlayers(); buildHeat(); fillHeatPlayers();
  } catch (e) { S.trackState = 'error'; S.view = 'play'; }
  viewButtons();
}
// Officials sit after the 22 players in each frame. Offside follows Law 11: an attacker in the
// opponents' half nearer their goal line than both the ball and the second-to-last defender.
const OFFICIAL_MARK = { ref: 'R', ar1: 'A', ar2: 'A', fourth: '4' };
// Trails: each second of the last 4 is a segment, colored by speed, in FIFA's World Cup zones:
// under 15 km/h (walking, jogging) no segment; 15 to 20 running; 20 to 25 high-speed; over 25 sprint.
const TRAIL_S = 4, JOG_MPS = 15 / 3.6, HSR_MPS = 20 / 3.6, SPRINT_MPS = 25 / 3.6;
function offsideLine(frame, defending, at) {
  const T = S.track, depthOf = (x) => (defending === 'home' ? x : 105 - x);
  const depths = T.players.map((p, i) => [p, i]).filter(([p]) => p.team === defending && !offPitch(p))
    .map(([, i]) => depthOf(at(2 + 2 * i))).sort((p, q) => p - q);
  return Math.min(depths[1], depthOf(at(0)), 52.5);
}
const offPitch = (p) => p.sent_off_s != null && S.t >= p.sent_off_s;
// The ball's height from its flights: a parabola from start to end ([t0, t1, peak, end height]).
function ballZ(t) {
  const F = S.track.flights || [];
  let lo = 0, hi = F.length - 1, k = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (F[m][0] <= t) { k = m; lo = m + 1; } else hi = m - 1; }
  for (let j = k; j >= 0 && F[j][0] > t - 25; j--) {
    const [t0, t1, peak, zEnd] = F[j];
    if (t0 <= t && t <= t1 && t1 > t0) { const u = (t - t0) / (t1 - t0); return Math.max(0, 4 * peak * u * (1 - u) + zEnd * u); }
  }
  return 0;
}
function buildPlayers() {
  const svg = $('pitch'), g = sv('g', {}), T = S.track;
  const offLine = sv('line', { y1: 0, y2: 68, stroke: 'var(--ink)', 'stroke-width': 0.35 });
  const lead = sv('g', {});          // the lead-up to a picked key moment, under the players
  g.append(offLine, lead);
  const trails = T.players.map(() => { const segs = []; for (let k = 0; k < TRAIL_S; k++) { const l = sv('line', { 'stroke-linecap': 'round' }); g.append(l); segs.push(l); } return segs; });
  const dots = T.players.map((p) => {
    const d = sv('g', {});           // hover labels come from showTip, not a <title>
    // Broadcast style: every dot has a thin light edge, so any kit color reads on the green pitch.
    const c = sv('circle', { r: 1.75, fill: `var(--${p.team})`, stroke: 'var(--ink)', 'stroke-width': p.goalkeeper ? 0.5 : 0.22 });
    const n = sv('text', { 'font-size': p.number > 9 ? 1.35 : 1.6, 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: `var(--${p.team}-on)`, 'font-family': 'var(--mono)', 'font-weight': 700 });
    n.textContent = p.number; d.append(c, n); g.append(d);
    return { d, c, n };
  });
  const offRings = T.players.map(() => { const r = sv('circle', { r: 2.5, fill: 'none', stroke: 'var(--bad)', 'stroke-width': 0.5 }); g.append(r); return r; });
  const ring = sv('circle', { r: 2.7, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 0.45 });
  const ball = sv('circle', { r: 0.85, fill: 'var(--ink)', stroke: 'var(--paper)', 'stroke-width': 0.3 });
  const recvRing = sv('circle', { r: 3.1, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 0.4, 'stroke-dasharray': '0.8 0.6' });
  // Ball height: a shadow stays on the grass; the ball rises above it (drawn higher up the page)
  // and a thin stalk joins them. Over a metre up, the height is written beside it.
  const shadow = sv('ellipse', { rx: 0.9, ry: 0.45, fill: 'var(--ink)', opacity: 0.35 });
  const stalk = sv('line', { stroke: 'var(--ink)', 'stroke-width': 0.18, opacity: 0.6 });
  const zText = sv('text', { 'font-size': 1.9, fill: 'var(--ink)', 'font-family': 'var(--mono)', 'font-weight': 700 });
  g.append(ring, shadow, stalk, ball, zText, recvRing);
  const officials = (T.officials || []).map((o) => {
    const d = sv('g', {});
    const r = sv('rect', { width: 2.6, height: 2.6, fill: 'var(--ink)' });
    const t = sv('text', { 'font-size': 1.7, 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: 'var(--paper)', 'font-family': 'var(--mono)', 'font-weight': 700 });
    t.textContent = OFFICIAL_MARK[o.id] || '?'; d.append(r, t); g.append(d);
    return { r, t };
  });
  // A picked key moment: a thick ring on each player involved, and a label on the main one.
  const focus = [0, 1].map(() => sv('circle', { r: 3.3, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 0.7 }));
  const callout = sv('g', {}), calloutBox = sv('rect', { fill: 'var(--ink)', rx: 0.4 });
  const calloutText = sv('text', { fill: 'var(--paper)', 'font-size': 2.3, 'font-family': 'var(--ui)', 'font-weight': 700, 'dominant-baseline': 'central' });
  callout.append(calloutBox, calloutText);
  g.append(...focus, callout);
  svg.append(g);
  playersLayer = { g, dots, ring, ball, offLine, trails, offRings, officials, recvRing, shadow, stalk, zText, lead, leadKey: '',
                   focus, callout, calloutBox, calloutText, aria: '', note: '' };
}
// A picked key moment: the players involved are ringed, the main one labelled ("Goal: 7 Leon
// Mbeki"), and everyone else dimmed, so the eye goes to the right place.
function drawFocus(L, at, now) {
  const m = S.pick && S.moment, T = S.track;
  const slots = m ? [m.actor, m.other].map((n) => (n ? T.players.findIndex((p) => p.name === n) : -1)) : [-1, -1];
  T.players.forEach((p, i) => { L.dots[i].d.style.opacity = m && !slots.includes(i) ? 0.35 : 1; });
  L.ring.style.display = m ? 'none' : '';        // the usual "nearest the ball" ring would compete
  L.focus.forEach((c, j) => {
    const i = slots[j];
    c.style.display = i >= 0 ? '' : 'none';
    if (i >= 0) { c.setAttribute('cx', MX(at(2 + 2 * i), now)); c.setAttribute('cy', MY(at(3 + 2 * i), now)); }
  });
  const i = slots[0];
  L.callout.style.display = i >= 0 ? '' : 'none';
  if (i < 0) return;
  const p = T.players[i], text = `${m.what}: ${p.number} ${p.name}`;
  const w = text.length * 1.2 + 2, x = Math.min(105 - w, Math.max(0, MX(at(2 + 2 * i), now) - w / 2));
  const yDot = MY(at(3 + 2 * i), now), y = yDot > 10 ? yDot - 7.5 : yDot + 4.5;
  L.calloutBox.setAttribute('x', x); L.calloutBox.setAttribute('y', y); L.calloutBox.setAttribute('width', w); L.calloutBox.setAttribute('height', 3.4);
  L.calloutText.setAttribute('x', x + 1); L.calloutText.setAttribute('y', y + 1.75); L.calloutText.textContent = text;
}
// A picked key moment keeps every player on the pitch and adds its lead-up: the last 8 actions.
function drawLead(L) {
  const key = S.pick ? `${lastEventIndex(S.t)}|${S.flip}` : '';
  if (key === L.leadKey) return;
  L.leadKey = key;
  if (!key) { L.lead.replaceChildren(); return; }
  drawActions(L.lead, lastEventIndex(S.t), 8, false);
}
function drawPlayers() {
  const T = S.track, L = playersLayer, n = T.frames.length - 1, Tx = TXT[S.lang];
  const f0 = Math.min(n, Math.floor(S.t)), f1 = Math.min(n, f0 + 1), a = S.t - f0;
  const A = T.frames[f0], B = T.frames[f1], raw = (k) => (A[k] + (B[k] - A[k]) * a) / 10;
  // Dots and the ball come from motion.js (smooth curves, the ball at its exact touches). The
  // offside line and rings use the 1 Hz frames, so each decision is exactly what the events say.
  const Mf = S.motion ? S.motion.live(S.t) : null, at = Mf ? (k) => Mf[k] : raw;
  const bx = at(0), by = at(1), z = ballZ(S.t), now = S.t;
  const gx = MX(bx, now), gy = MY(by, now), lift = z * 0.45;
  L.shadow.setAttribute('cx', gx); L.shadow.setAttribute('cy', gy);
  L.ball.setAttribute('cx', gx); L.ball.setAttribute('cy', gy - lift); L.ball.setAttribute('r', 0.85 + Math.min(0.6, z * 0.04));
  L.stalk.setAttribute('x1', gx); L.stalk.setAttribute('x2', gx); L.stalk.setAttribute('y1', gy); L.stalk.setAttribute('y2', gy - lift);
  L.stalk.style.display = L.shadow.style.display = z > 0.3 ? '' : 'none';
  L.zText.style.display = z >= 1 ? '' : 'none';
  if (z >= 1) { L.zText.setAttribute('x', gx + 1.6); L.zText.setAttribute('y', gy - lift - 0.6); L.zText.textContent = Tx.up(num1(z)); }
  // Who is defending: around a frozen through ball, the side it was played against; else the
  // side without the ball this second.
  if (S.freeze != null && Math.abs(S.t - T.through[S.freeze].frame) > 0.5) S.freeze = null;
  const fz = S.freeze != null ? T.through[S.freeze] : null;
  const attacking = fz ? fz.team : (T.possession[f0] === 'h' ? 'home' : 'away');
  const defending = attacking === 'home' ? 'away' : 'home';
  const line = offsideLine(f0, defending, raw), toX = (d) => MX(defending === 'home' ? d : 105 - d, now);
  L.offLine.setAttribute('x1', toX(line)); L.offLine.setAttribute('x2', toX(line));
  // While the ball is out of play there is no offside (and none at all from a corner or throw-in).
  const dead = !fz && currentCard() != null;
  L.offLine.style.display = dead ? 'none' : '';
  let near = null, best = 1e9, offN = 0;
  T.players.forEach((p, i) => {
    const dx = at(2 + 2 * i), dy = at(3 + 2 * i), dot = L.dots[i], gone = offPitch(p);
    const x = MX(dx, now), y = MY(dy, now);
    dot.d.style.display = gone ? 'none' : '';
    dot.c.setAttribute('cx', x); dot.c.setAttribute('cy', y); dot.n.setAttribute('x', x); dot.n.setAttribute('y', y);
    const dist = gone ? 1e9 : Math.hypot(x - gx, y - gy); if (dist < best) { best = dist; near = [x, y]; }
    // In an offside position: an attacker nearer the defenders' goal line than the offside line.
    const rx = raw(2 + 2 * i), off = !dead && !gone && p.team === attacking && (defending === 'home' ? rx : 105 - rx) < line;
    L.offRings[i].style.display = off ? '' : 'none';
    if (off) { offN++; L.offRings[i].setAttribute('cx', x); L.offRings[i].setAttribute('cy', y); }
    // The trail: one segment per second, newest last, colored by the speed in that second.
    // Running is pale, high-speed solid, a sprint purple; older seconds fade.
    const P = (k) => [MX(T.frames[k][2 + 2 * i] / 10, now), MY(T.frames[k][3 + 2 * i] / 10, now)];
    L.trails[i].forEach((seg, j) => {
      const k1 = f0 - (TRAIL_S - 1 - j), k0 = k1 - 1;
      const end = j === TRAIL_S - 1 ? [x, y] : (k1 >= 0 ? P(k1) : null), start = k0 >= 0 ? P(k0) : null;
      const v = start && k1 >= 0 ? Math.hypot(T.frames[k1][2 + 2 * i] - T.frames[k0][2 + 2 * i], T.frames[k1][3 + 2 * i] - T.frames[k0][3 + 2 * i]) / 10 : 0;
      if (gone || !start || !end || v < JOG_MPS) { seg.style.display = 'none'; return; }
      const age = (TRAIL_S - 1 - j) / TRAIL_S, sprint = v >= SPRINT_MPS, hsr = v >= HSR_MPS;
      seg.style.display = '';
      seg.setAttribute('x1', start[0]); seg.setAttribute('y1', start[1]); seg.setAttribute('x2', end[0]); seg.setAttribute('y2', end[1]);
      seg.setAttribute('stroke', sprint ? 'var(--sprint)' : `var(--${p.team})`);
      seg.setAttribute('stroke-width', sprint ? 0.9 : (hsr ? 0.7 : 0.5));
      seg.setAttribute('opacity', ((sprint || hsr) ? 0.95 : 0.4) * (1 - 0.6 * age));
    });
  });
  L.ring.setAttribute('cx', near[0]); L.ring.setAttribute('cy', near[1]);
  drawFocus(L, at, now);
  // Frozen on a through ball: the receiver comes to the front with a dashed ring.
  L.recvRing.style.display = fz ? '' : 'none';
  if (fz) {
    const i = fz.receiver_slot, x = MX(at(2 + 2 * i), now), y = MY(at(3 + 2 * i), now);
    L.recvRing.setAttribute('cx', x); L.recvRing.setAttribute('cy', y);
    if (L.g.lastChild !== L.dots[i].d) { L.g.append(L.dots[i].d); }
  }
  // Hover targets: where each player and official is now, with his label and speed this second.
  const kmh = (k) => Math.round(Math.hypot(B[k] - A[k], B[k + 1] - A[k + 1]) / 10 * 3.6);
  L.hits = [];
  T.players.forEach((p, i) => {
    if (offPitch(p)) return;
    L.hits.push({ id: p.id, x: MX(at(2 + 2 * i), now), y: MY(at(3 + 2 * i), now),
                  text: Tx.hoverPlayer(p.number, p.name, p.position, S.data.clubs[p.team], kmh(2 + 2 * i)) });
  });
  L.officials.forEach((o, j) => {
    const x = MX(at(46 + 2 * j), now), y = MY(at(47 + 2 * j), now);
    o.r.setAttribute('x', x - 1.3); o.r.setAttribute('y', y - 1.3); o.t.setAttribute('x', x); o.t.setAttribute('y', y);
    L.hits.push({ id: T.officials[j].id, x, y, text: Tx.hoverOfficial(Tx.officialName[T.officials[j].id], kmh(46 + 2 * j)) });
  });
  const club = S.data.clubs[defending], d = Math.round(line);
  const aria = Tx.playersAria(minLabel(S.t), club, d, offN);
  if (aria !== L.aria) { L.aria = aria; $('pitch').setAttribute('aria-label', aria); }
  const note = (S.pick ? Tx.leadNote : '') + Tx.notePlayers(club, d, offN, dead);
  if (note !== L.note) { L.note = note; $('pitch-note').textContent = note; }
  throughButtons();
  drawLead(L);
}
// Key moments: one drop-down, grouped: goals, penalties, cards, big chances, saves, corners and,
// once positions are loaded, through balls. Only moments that have already happened are listed. Picking one pauses there and says what happened.
// A through ball pauses at the second before the pass and gives the offside margin.
function throughButtons() { momentsMenu(); }
// The full list is built once per language and tracking state; the menu shows only the moments
// that have happened by the furthest minute reached (newest first), as in a live match.
const MOM = { key: '', groups: [] };
function momentItems() {
  const key = `${S.lang}|${S.trackState}`;
  if (MOM.key !== key) { MOM.key = key; MOM.groups = allMomentItems(); }
  // The live edge: the furthest minute reached. Replaying a moment or scrubbing back keeps the
  // later moments listed; they have already happened.
  S.edge = Math.max(S.edge || 0, S.t);
  const horizon = S.edge;
  return MOM.groups.map((g) => ({ ...g, list: g.list.filter((it) => it.t <= horizon + 0.01).reverse() })).filter((g) => g.list.length);
}
function allMomentItems() {
  const D = S.data, ev = D.timeline.events, types = D.timeline.event_types, Tx = TXT[S.lang], G = Tx.km;
  const xgOf = Object.fromEntries(D.timeline.notable.filter((n) => n.type === 'shot').map((n) => [n.t + '|' + n.player, n.xg]));
  const groups = { goal: [], penalty: [], card: [], chance: [], save: [], corner: [], through: [] };
  ev.forEach((e, k) => {
    const type = types[e[1]], id = `e${String(k + 1).padStart(6, '0')}`;
    const item = (g) => groups[g].push({ value: `e:${k}`, t: e[0], id });
    if (type === 'shot') {
      const xg = xgOf[e[0] + '|' + e[8]];
      if (e[7] === 'goal') item('goal');
      else if (xg != null && xg >= 0.3) item('chance');
    } else if (type === 'restart' && e[10] === 'penalty') item('penalty');
    else if (type === 'foul' && (e[10] === 'yellow' || e[10] === 'red')) item('card');
    else if (type === 'save') item('save');
    else if (type === 'restart' && e[10] === 'corner') item('corner');
  });
  if (S.trackState === 'ready') S.track.through.forEach((b, k) => groups.through.push({ value: `t:${k}`, t: b.t, through: b }));
  return Object.entries(groups).filter(([, list]) => list.length).map(([g, list]) => ({ g, label: G.groups[g], list }));
}
function momentText(it) {
  const Tx = TXT[S.lang];
  if (it.through) { const b = it.through; return Tx.tbOption(minLabel(b.t), b.passer, b.receiver, Tx.tbOutcome[b.outcome]); }
  const d = describe(it.id);
  return `${minLabel(it.t)} ${d.what}: ${d.who}`;
}
function momentsMenu() {
  const Tx = TXT[S.lang], sel = $('tb-pick');
  const groups = momentItems(), count = groups.reduce((n, g) => n + g.list.length, 0);
  const key = `${S.lang}|${S.trackState}|${count}`;
  if (sel.dataset.key !== key) {
    sel.dataset.key = key; $('tb-label').textContent = Tx.km.label; $('tb-again').textContent = Tx.km.again;
    sel.replaceChildren(el('option', { value: '' }, count ? Tx.km.choose : Tx.km.none),
      ...groups.map((grp) => { const og = document.createElement('optgroup'); og.label = `${grp.label} (${grp.list.length})`;
        og.append(...grp.list.map((it) => el('option', { value: it.value }, momentText(it)))); return og; }));
  }
  // The choice stays shown while the replay stays at that moment.
  if (S.pick && !S.replay && (S.playing || Math.abs(S.t - S.pick.t) > 1.5)) {
    S.pick = null; S.moment = null; $('tb-again').hidden = true; $('tb-caption').textContent = ''; delete $('tb-caption').dataset.frame;
  }
  const want = S.pick ? S.pick.value : '';
  if (sel.value !== want) sel.value = want;
}
// Picking a moment plays it: the replay goes back a few seconds, plays the lead-up at 1.5x real
// time (the fading lines build up as it goes), and stops on the moment. The players involved are
// ringed and labelled; everyone else is dimmed. "Play it again" repeats it.
const LEAD_S = 8, REPLAY_SPEED = 1.5;
function pickMoment(value) {
  const Tx = TXT[S.lang];
  if (S.view === 'play') setView('players');        // keep every player on the pitch, with the lead-up
  setPlaying(false); S.freeze = null;
  let at, what, actor, other = null, onEnd = null, caption;
  if (value.startsWith('t:')) {
    const k = +value.slice(2), b = S.track.through[k];
    at = b.frame; actor = b.passer; other = b.receiver; what = TXT[S.lang].ev.through;
    onEnd = () => freezeThrough(k);
    caption = Tx.tbOption(minLabel(b.t), b.passer, b.receiver, Tx.tbOutcome[b.outcome]);
  } else {
    const k = +value.slice(2), e = S.data.timeline.events[k], id = `e${String(k + 1).padStart(6, '0')}`, d = describe(id);
    // A corner or penalty stops one second before the kick, with the players set up.
    const restart = S.data.timeline.event_types[e[1]] === 'restart';
    at = Math.max(0, restart ? e[0] - 1 : e[0] + 0.3);
    actor = e[8]; what = d.what;
    const n = S.data.timeline.notable.find((x) => x.event_id === id);
    caption = Tx.km.caption(minLabel(e[0]), d.what, d.who, n && n.xg != null ? num2(n.xg) : null);
  }
  S.moment = { actor, other, what };
  S.pick = { value, t: at };
  $('tb-caption').textContent = caption; $('tb-caption').dataset.frame = String(Math.floor(at));
  // The lead-up always plays, also with reduced motion on: it is the replay the viewer asked for,
  // like pressing Play, not a decoration. (Before 2026-10-26 reduced motion skipped it, so
  // "Play it again" did nothing.)
  S.t = Math.max(0, at - LEAD_S); S.replay = { to: at, onEnd };
  $('tb-again').hidden = false;
}
$('tb-again').addEventListener('click', () => { if (S.pick) { const v = S.pick.value; pickMoment(v); } });
function freezeThrough(k) {
  const T = S.track, b = T.through[k], Tx = TXT[S.lang];
  setPlaying(false); S.t = b.frame; S.freeze = k;
  const at = (i) => T.frames[b.frame][i] / 10, defending = b.team === 'home' ? 'away' : 'home';
  const line = offsideLine(b.frame, defending, at), rx = at(2 + 2 * b.receiver_slot);
  const margin = (defending === 'home' ? rx : 105 - rx) - line;
  $('tb-caption').textContent = Tx.tbCaption(minLabel(b.t), who(b.passer), who(b.receiver), margin, b.outcome);
  $('tb-caption').dataset.frame = String(b.frame);
}
$('tb-pick').addEventListener('change', (e) => { if (e.target.value !== '') pickMoment(e.target.value); });
function viewButtons() {
  const T = TXT[S.lang], label = { play: T.viewPlay, players: T.viewPlayers, heat: T.viewHeat, shape: T.viewShape, running: T.viewRunning };
  document.querySelectorAll('.view button').forEach((b) => {
    const v = b.dataset.view, on = v === S.view, waiting = v !== 'play' && S.trackState === 'loading';
    b.setAttribute('aria-pressed', String(on));
    b.textContent = waiting && on ? T.loading : label[v];
    b.disabled = waiting;
  });
  const heatOn = S.view === 'heat' && S.trackState === 'ready';
  $('heat-controls').hidden = !heatOn; $('heat-legend').hidden = !heatOn;
  $('through-controls').hidden = !(S.view === 'play' || ((S.view === 'players' || S.view === 'running') && S.trackState === 'ready'));
  if (S.data) $('tb-pick').dataset.key = '';
  $('run-table').hidden = !(S.view === 'running' && S.trackState === 'ready');
  $('pitch-hint').hidden = !(S.view === 'players' || S.view === 'running');   // zoom, labels and the camera
  $('flip-label').textContent = T.flip;
  if (runKey) runKey.k = '';
  const shapeOn = S.view === 'shape' && S.trackState === 'ready';
  $('shape-controls').hidden = !shapeOn; $('shape-table').hidden = !shapeOn; $('shape-caption').hidden = !shapeOn;
  $('shape-team').setAttribute('aria-label', T.team); $('shape-state').setAttribute('aria-label', T.phase);
  document.querySelectorAll('#shape-team button').forEach((b) => {
    b.textContent = S.data ? S.data.clubs[b.dataset.team] : b.textContent;
    b.setAttribute('aria-pressed', String(b.dataset.team === S.shapeTeam));
  });
  document.querySelectorAll('#shape-state button').forEach((b) => {
    b.textContent = b.dataset.state === 'out' ? T.without : T.withBall;
    b.setAttribute('aria-pressed', String(b.dataset.state === S.shapeState));
  });
  if (shapeLayer) shapeLayer.key = '';
  $('heat-team').setAttribute('aria-label', T.team); $('heat-player-label').textContent = T.player;
  document.querySelectorAll('#heat-team button').forEach((b) => {
    b.textContent = b.dataset.team === 'officials' ? T.officials : (S.data ? S.data.clubs[b.dataset.team] : b.textContent);
    b.setAttribute('aria-pressed', String(b.dataset.team === S.heatTeam));
  });
  $('heat-less').textContent = T.less; $('heat-more').textContent = T.more;
  if (S.trackState === 'error') $('pitch-note').textContent = T.noTrack;
  else if (S.view === 'play') $('pitch-note').textContent = T.notePlay;
  if (S.view === 'play') $('pitch').setAttribute('aria-label', S.lang === 'es' ? 'El campo: la última jugada' : 'The pitch: the latest play');
  if (playersLayer) { playersLayer.aria = ''; playersLayer.note = ''; }
  if (heatLayer) heatLayer.key = '';
}
function setView(v) {
  S.view = v; viewButtons();
  if (v !== 'play') loadTracking();
}
document.querySelectorAll('.view button').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
// ---------------------------------------------------------------- pitch: heat map of ground covered
// For each second up to now, the distance each selected player ran goes to the zone at the
// middle of that run. A zone's share = its distance / all the distance. Five color steps,
// scaled to the busiest zone. The text color per step keeps 4.5:1 (WCAG AA).
// Officials use an ink scale; its middle step is lighter (0.42) so dark text keeps 4.5:1.
const HEAT_ALPHA = { home: [0.12, 0.3, 0.5, 0.72, 0.95], away: [0.12, 0.3, 0.5, 0.72, 0.95], officials: [0.12, 0.3, 0.42, 0.72, 0.95] };
// Who the heat map covers, as [name, frame offset of x] pairs.
function heatSlots() {
  const T = S.track;
  if (S.heatTeam === 'officials') {
    return T.officials.map((o, j) => [o.id, 46 + 2 * j]).filter(([id]) => !S.heatPlayer || id === S.heatPlayer);
  }
  return T.players.map((p, i) => [p, 2 + 2 * i]).filter(([p]) => p.team === S.heatTeam && (!S.heatPlayer || p.id === S.heatPlayer));
}
function cssColor(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function blend(fg, bg, a) {
  const f = [1, 3, 5].map((i) => parseInt(fg.slice(i, i + 2), 16)), b = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16));
  return '#' + f.map((v, i) => Math.round(b[i] + (v - b[i]) * a).toString(16).padStart(2, '0')).join('');
}
// ---------------------------------------------------------------- kit colors (chosen by the viewer)
// A club color is used three ways: as a fill (dots, bars, chart), as text on the dark page, and
// under shirt numbers. Text must keep 4.5:1, so a dark kit color is lightened toward ink for text
// only; numbers and heat-map labels use white or the page color, whichever has more contrast.
function lum(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function contrast(a, b) { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); }
// Defaults for the dark broadcast page (2026-10-27): brighter than the old paper-page kits.
const KIT_DEFAULT = { home: '#4a8ae8', away: '#e8834a' };
const KIT_OLD = { home: '#1f4e9c', away: '#a24a1d' };
function applyKit(team, hex) {
  const root = document.documentElement.style, paper = cssColor('--paper'), ink = cssColor('--ink');
  let text = hex;
  for (let k = 0.1; contrast(text, paper) < 4.5 && k <= 1.01; k += 0.1) text = blend(ink, hex, k);
  root.setProperty(`--${team}`, hex); root.setProperty(`--${team}-ink`, text);
  root.setProperty(`--${team}-on`, contrast('#ffffff', hex) >= contrast(paper, hex) ? '#ffffff' : paper);
  $(`kit-${team}`).value = hex;
  if (heatLayer) heatLayer.key = '';
  kitWarning();
}
function kitWarning() {
  const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const a = rgb($('kit-home').value), b = rgb($('kit-away').value);
  $('kit-warn').hidden = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) >= 90;
  $('kit-warn').textContent = TXT[S.lang].kitWarn;
}
function saveKits() { try { localStorage.setItem('sixth.kits', JSON.stringify({ home: $('kit-home').value, away: $('kit-away').value })); } catch (e) { /* not kept */ } }
function loadKits() {
  let k = null;
  try { k = JSON.parse(localStorage.getItem('sixth.kits') || 'null'); } catch (e) { k = null; }
  for (const team of ['home', 'away']) applyKit(team, (k && /^#[0-9a-f]{6}$/i.test(k[team] || '') && k[team].toLowerCase() !== KIT_OLD[team] ? k[team] : KIT_DEFAULT[team]));
}
for (const team of ['home', 'away']) $(`kit-${team}`).addEventListener('input', (e) => { applyKit(team, e.target.value); saveKits(); });
$('kit-reset').addEventListener('click', () => { applyKit('home', KIT_DEFAULT.home); applyKit('away', KIT_DEFAULT.away); saveKits(); });
function kitWords() {
  const T = TXT[S.lang];
  $('kits-label').textContent = T.kits; $('kit-reset').textContent = T.reset; $('kit-warn').textContent = T.kitWarn;
  if (S.data) { $('kit-home-name').textContent = S.data.clubs.home; $('kit-away-name').textContent = S.data.clubs.away; }
}
function buildHeat() {
  heatLayer.g.replaceChildren(); heatLayer.tg.replaceChildren(); heatLayer.cells = []; heatLayer.key = '';
  for (let r = 0; r < 3; r++) for (let c = 0; c < 6; c++) {
    const rect = sv('rect', { x: c * ZONE_W, y: r * ZONE_H, width: ZONE_W, height: ZONE_H, fill: 'none' });
    const text = sv('text', { x: (c + 0.5) * ZONE_W, y: (r + 0.5) * ZONE_H, 'text-anchor': 'middle', 'dominant-baseline': 'central',
                              'font-size': 2.8, 'font-family': 'var(--mono)', 'font-weight': 700 });
    heatLayer.g.append(rect); heatLayer.tg.append(text); heatLayer.cells.push({ rect, text });
  }
}
function fillHeatPlayers() {
  const sel = $('heat-player'), T = TXT[S.lang];
  if (S.heatTeam === 'officials') {
    sel.replaceChildren(el('option', { value: '' }, T.allOfficials),
      ...S.track.officials.map((o) => el('option', { value: o.id }, T.officialName[o.id])));
  } else {
    sel.replaceChildren(el('option', { value: '' }, T.wholeTeam),
      ...S.track.players.filter((p) => p.team === S.heatTeam).map((p) => el('option', { value: p.id }, `${p.number} ${p.name}, ${p.position}`)));
  }
  sel.value = S.heatPlayer;
}
function zoneLabel(k, team) {
  const T = TXT[S.lang], c = k % 6, r = Math.floor(k / 6);
  const third = team === 'home' ? Math.floor(c / 2) : 2 - Math.floor(c / 2);
  const ch = team === 'home' ? r : 2 - r;      // facing the goal you attack, left is the top for home
  return T.zoneName(T.thirds[third], T.channels[ch]);
}
function drawHeat() {
  const T = TXT[S.lang], last = Math.min(S.track.frames.length - 1, Math.floor(S.t));
  const key = [S.heatTeam, S.heatPlayer, last, S.lang].join('|');
  if (key === heatLayer.key) return;
  heatLayer.key = key;
  const offsets = heatSlots().map(([, o]) => o);
  const acc = new Array(18).fill(0), F = S.track.frames;
  for (let f = 1; f <= last; f++) {
    const A = F[f - 1], B = F[f];
    for (const o of offsets) {
      const x0 = A[o], y0 = A[o + 1], x1 = B[o], y1 = B[o + 1];
      const d = Math.hypot(x1 - x0, y1 - y0); if (!d) continue;
      // Officials outside the touchlines count in the nearest zone.
      const mx = Math.min(104.9, Math.max(0, (x0 + x1) / 20)), my = Math.min(67.9, Math.max(0, (y0 + y1) / 20));
      acc[Math.min(2, Math.floor(my / ZONE_H)) * 6 + Math.min(5, Math.floor(mx / ZONE_W))] += d;
    }
  }
  const total = acc.reduce((a, b) => a + b, 0), max = Math.max(...acc);
  const tone = S.heatTeam === 'officials' ? '--ink' : `--${S.heatTeam}`, alpha = HEAT_ALPHA[S.heatTeam];
  const base = cssColor('--pitch'), club = cssColor(tone), white = '#ffffff', ink = cssColor('--ink'), dark = cssColor('--paper');
  heatLayer.cells.forEach((cell, k) => {
    const share = total ? acc[k] / total : 0, step = share > 0 ? Math.max(1, Math.ceil(5 * acc[k] / max)) - 1 : -1;
    cell.rect.setAttribute('fill', step < 0 ? 'none' : blend(club, base, alpha[step]));
    const bg = step < 0 ? base : blend(club, base, alpha[step]);
    cell.text.setAttribute('fill', step < 0 ? ink : (contrast(white, bg) >= contrast(dark, bg) ? white : dark));
    cell.text.textContent = share >= 0.005 ? `${Math.round(share * 100)}%` : '';
  });
  document.querySelectorAll('#heat-legend i').forEach((sw, k) => { sw.style.background = blend(club, base, alpha[k]); });
  let who;
  if (S.heatTeam === 'officials') who = S.heatPlayer ? T.officialWho[S.heatPlayer] : T.allWho;
  else { const p = S.heatPlayer && S.track.players.find((x) => x.id === S.heatPlayer); who = p ? p.name : S.data.clubs[S.heatTeam]; }
  $('pitch-note').textContent = total ? T.heatNote(who, minLabel(S.t)) + (S.flip ? T.flatNote : '') : T.heatEmpty;
  const top = acc.indexOf(max);
  $('pitch').setAttribute('aria-label', total ? T.heatAria(who, minLabel(S.t), zoneLabel(top, S.heatTeam === 'away' ? 'away' : 'home'), Math.round(100 * max / total)) : T.heatEmpty);
}
document.querySelectorAll('#heat-team button').forEach((b) => b.addEventListener('click', () => {
  S.heatTeam = b.dataset.team; S.heatPlayer = ''; viewButtons(); fillHeatPlayers();
}));
$('heat-player').addEventListener('change', (e) => { S.heatPlayer = e.target.value; heatLayer.key = ''; });

// ---------------------------------------------------------------- pitch: shape (formation) by 15-minute block
// From /api/tracking `shape` (sixth/formations.py). Only completed blocks are shown: the page never
// shows what has not happened yet.
function shapeSetup(team, t) {
  let name = null;
  for (const c of S.track.shape[team].setup) if (c.from_s <= t) name = c.formation;
  return name;
}
function doneBlocks(team) { return S.track.shape[team].blocks.filter((b) => b.to_s <= S.t + 0.5); }
// Live (2026-10-27): unless the viewer picks a block in the table, the pitch shows the shape over
// the last 15 minutes (or since kick-off), refreshed every 5 minutes, so it appears from 5'.
function liveWindows(team) { return (S.track.shape[team].rolling || []).filter((w) => w.to_s <= S.t + 0.5); }
function drawShape() {
  const T = TXT[S.lang], team = S.shapeTeam, done = doneBlocks(team), roll = liveWindows(team);
  const live = S.shapeBlock == null || S.shapeBlock >= done.length;
  const k = live ? -1 : S.shapeBlock;
  const key = [team, S.shapeState, done.length, roll.length, k, S.lang].join('|');
  if (key === shapeLayer.key) return;
  shapeLayer.key = key;
  const g = shapeLayer.g; g.replaceChildren(); shapeLayer.hits = [];
  const club = S.data.clubs[team];
  drawShapeTable(team, done, k);
  $('shape-live').setAttribute('aria-pressed', String(live)); $('shape-live').textContent = T.shapeLive;
  $('pitch-note').textContent = T.shapeNote + (S.flip ? T.flatNote : '');
  const b = live ? roll[roll.length - 1] : done[k];
  if (!b) { $('shape-caption').textContent = T.shapeWait(club); $('pitch').setAttribute('aria-label', T.shapeWait(club)); return; }
  const r = b[S.shapeState], phase = S.shapeState === 'out' ? T.without : T.withBall;
  const blockName = T.blockName(b.from_s / 60, b.to_s / 60), setup = shapeSetup(team, (b.from_s + b.to_s) / 2);
  if (!r) { $('shape-caption').textContent = T.shapeNone; return; }
  // Lines first (player to slot), then the slots, then the players on top.
  const players = S.track.players.filter((p) => p.team === team && !p.goalkeeper);
  r.players.forEach(([x, y], i) => {
    const [sx, sy] = r.slots[r.assign[i]];
    g.append(sv('line', { x1: x, y1: y, x2: sx, y2: sy, stroke: 'var(--muted)', 'stroke-width': 0.3 }));
  });
  r.slots.forEach(([x, y]) => g.append(sv('circle', { cx: x, cy: y, r: 2.0, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 0.35, 'stroke-dasharray': '0.6 0.5' })));
  r.players.forEach(([x, y], i) => {
    const d = sv('g', {});
    shapeLayer.hits.push({ id: players[i].id, x, y, text: `${players[i].number} ${players[i].name}, ${players[i].position}, ${S.data.clubs[team]}` });
    d.append(sv('circle', { cx: x, cy: y, r: 1.75, fill: `var(--${team})`, stroke: 'var(--ink)', 'stroke-width': 0.22 }));
    const n = sv('text', { x, y, 'font-size': players[i].number > 9 ? 1.35 : 1.6, 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: `var(--${team}-on)`, 'font-family': 'var(--mono)', 'font-weight': 700 });
    n.textContent = players[i].number; d.append(n); g.append(d);
  });
  let cap = (live ? T.liveTag : '') + T.shapeCaption(club, blockName, phase, r.best, num1(r.best_m), r.next, num1(r.next_m), setup);
  const typical = S.track.expected_shape[setup][S.shapeState];
  if (r.best !== setup && r.best === typical) cap += T.shapeTypical(setup, phase);
  else if (r.best !== typical) cap += T.shapeDrift(setup, num1(r.all_m[setup] || 0));
  $('shape-caption').textContent = cap;
  $('pitch').setAttribute('aria-label', cap);
}
function drawShapeTable(team, done, shown) {
  const T = TXT[S.lang], all = S.track.shape[team].blocks;
  $('shape-head').replaceChildren(...[T.minutes, T.setUp, T.without, T.withBall].map((h) => el('th', { scope: 'col' }, h)));
  const cell = (r, state) => {
    if (!r) return el('td', {}, '-');
    return el('td', {}, el('span', { class: 'f' }, r.best), el('span', { class: 'm' }, T.mOff(num1(r.best_m))));
  };
  $('shape-body').replaceChildren(...all.map((b, i) => {
    const complete = i < done.length;
    const mid = (b.from_s + b.to_s) / 2, set = shapeSetup(team, mid), start = shapeSetup(team, b.from_s);
    const change = S.track.shape[team].setup.find((c) => c.from_s > b.from_s && c.from_s < b.to_s);
    const btn = el('button', { type: 'button', class: 'blk', disabled: complete ? null : 'disabled',
                               onclick: () => { S.shapeBlock = i; shapeLayer.key = ''; } }, T.blockName(b.from_s / 60, b.to_s / 60));
    const setCell = el('td', { class: change ? 'changed' : null }, el('span', { class: 'f' }, change ? `${start} → ${change.formation}` : set),
      change ? el('span', { class: 'm' }, T.changedTo(change.formation, minLabel(change.from_s), T.why[change.why] || change.why)) : null);
    if (!complete) return el('tr', {}, el('td', {}, btn), el('td', { class: 'later', colspan: 3 }, '·'));
    return el('tr', { class: i === shown ? 'shown' : null }, el('td', {}, btn), setCell, cell(b.out, 'out'), cell(b.in, 'in'));
  }));
}
document.querySelectorAll('#shape-team button').forEach((b) => b.addEventListener('click', () => { S.shapeTeam = b.dataset.team; S.shapeBlock = null; viewButtons(); }));
$('shape-live').addEventListener('click', () => { S.shapeBlock = null; shapeLayer.key = ''; });
document.querySelectorAll('#shape-state button').forEach((b) => b.addEventListener('click', () => { S.shapeState = b.dataset.state; viewButtons(); }));

// ---------------------------------------------------------------- running, against Premier League means
// From /api/tracking `movement`: cumulative at each minute. Pace per 90 = so far x 5400 / seconds played.
const GROUP = { GK: null, LB: 'defender', RB: 'defender', LCB: 'defender', RCB: 'defender', CB: 'defender', LWB: 'defender', RWB: 'defender',
  LDM: 'midfielder', RDM: 'midfielder', CDM: 'midfielder', LCM: 'midfielder', CM: 'midfielder', RCM: 'midfielder', LM: 'midfielder', RM: 'midfielder', CAM: 'midfielder',
  LW: 'forward', RW: 'forward', ST: 'forward', LS: 'forward', RS: 'forward', SS: 'forward' };
function drawRunning() {
  const T = TXT[S.lang], R = T.run, M = S.track.movement, B = S.track.movement_benchmarks;
  const m = Math.min(90, Math.floor(S.t / 60)), key = `${m}|${S.lang}`;
  if (key === runKey.k) return;
  runKey.k = key;
  $('run-head').replaceChildren(...[R.player, R.pos, R.dist, R.walk, R.jog, R.run, R.hsr, R.spr, R.n, R.top, R.vs].map((h) => el('th', { scope: 'col' }, h)));
  const played = Math.max(60, m * 60), rows = [];
  for (const team of ['home', 'away']) {
    rows.push(el('tr', { class: 'team' }, el('td', { colspan: 11 }, S.data.clubs[team])));
    for (const p of S.track.players.filter((q) => q.team === team)) {
      const [d, walk, jog, run, hsr, spr, n, top] = M[p.id][m], g = GROUP[p.position], gone = p.sent_off_s != null && p.sent_off_s <= S.t;
      let vs = R.keeper;
      if (g) {
        const pace = d * 5400 / played, [mean, sd] = B[g].distance_m, zs = (pace - mean) / sd;
        vs = `${num1(pace / 1000)} km, ${zs > 1 ? R.high : zs < -1 ? R.low : R.typical} (${num1(mean / 1000)} ± ${num1(sd / 1000)})`;
      }
      if (gone) vs = R.off;
      rows.push(el('tr', { class: gone ? 'off' : null }, el('td', {}, `${p.number} ${p.name}`), el('td', {}, p.position),
        el('td', { class: 'n' }, num1(d / 1000)), ...[walk, jog, run, hsr, spr].map((v) => el('td', { class: 'n' }, String(v))),
        el('td', { class: 'n' }, String(n)), el('td', { class: 'n' }, String(Math.round(top / 10))), el('td', { class: 'vs' }, vs)));
    }
  }
  $('run-body').replaceChildren(...rows);
  $('pitch-note').textContent = R.note(minLabel(S.t));
}

// ---------------------------------------------------------------- the dead ball: a card while play is stopped
// Cards come from the match file (sixth/insights.py), computed from data up to the moment the ball
// went out. A card stays at least 6 s on screen, so it can be read at replay speed.
const STICKY_MS = 6000;
function currentCard() {
  const C = S.data.deadball; let lo = 0, hi = C.length - 1, k = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (C[m].t0 <= S.t) { k = m; lo = m + 1; } else hi = m - 1; }
  return k >= 0 && S.t <= C[k].t1 ? C[k] : null;
}
function pct(v) { return Math.round(v * 100); }
function barRow(label, rate, text, cls) {
  return [el('span', {}, label), el('span', { class: 'track' }, el('i', { class: `fill ${cls}`, style: `width:${Math.round(rate * 100)}%` })), el('span', { class: 'v' }, text)];
}
function drawDead(nowMs) {
  const card = currentCard(), box = $('dead');
  if (card && (!S.deadShown || S.deadShown.card !== card)) S.deadShown = { card, until: nowMs + STICKY_MS };
  const keep = S.deadShown && (S.deadShown.card === card || (nowMs < S.deadShown.until && S.t >= S.deadShown.card.t0 && S.t - S.deadShown.card.t1 < 240));
  if (!keep) { if (!box.hidden) { box.hidden = true; } S.deadShown = card ? S.deadShown : null; return; }
  const c = S.deadShown.card, T = TXT[S.lang], D = T.dead, club = S.data.clubs[c.team];
  const left = Math.max(0, Math.ceil(c.t1 - S.t)), key = `${c.event_id}|${left}|${S.lang}`;
  if (key === box.dataset.key) return;
  box.dataset.key = key; box.hidden = false;
  const kind = c.restart === 'free_kick' && c.direct ? D.direct : T.ev.restart[c.restart];
  const kids = [el('div', { class: 'head' }, el('span', { class: 'kind' }, `${D.out}: ${D.kind(kind, club)}`),
    el('span', { class: 'count' }, left > 0 ? D.restartIn(left) : ''))];
  const idx = c.team === 'home' ? 0 : 2;
  if (c.what_if) {
    const k = c.restart === 'free_kick' ? 'free_kick' : c.restart;
    kids.push(el('h3', {}, D.whatIf), el('p', {}, `${D.setPiece[k]} ${D.winNow(club, pct(c.win_now[idx]))} ${D.winIf(pct(c.what_if.win_if_goal[idx]))}`));
    kids.push(el('div', { class: 'bars' }, ...barRow(D.nowShort, c.win_now[idx], `${pct(c.win_now[idx])}%`, c.team),
      ...barRow(D.whatIf, c.what_if.win_if_goal[idx], `${pct(c.what_if.win_if_goal[idx])}%`, c.team)));
  }
  const f = c.finding;
  kids.push(el('h3', {}, D.last5));
  if (!f) kids.push(el('p', { class: 'verdict plain' }, D.none));
  else {
    const fc = S.data.clubs[f.team];
    kids.push(el('p', {}, D.metric[f.metric](fc)));
    if (f.metric === 'shots') kids.push(el('p', {}, D.shotsLine(f.now_k, num1(f.expected))));
    else kids.push(el('div', { class: 'bars' }, ...barRow(D.now, f.now_rate, `${pct(f.now_rate)}% (${D.of(f.now_k, f.now_n)})`, f.team),
      ...barRow(D.before, f.before_rate, `${pct(f.before_rate)}% (${D.of(f.before_k, f.before_n)})`, 'before')));
    kids.push(f.significant ? el('p', { class: 'verdict' }, D.unusual(Math.max(20, Math.round(1 / Math.max(f.p_adj, 1e-4)))))
      : el('p', { class: 'verdict plain' }, D.normal));
  }
  box.replaceChildren(...kids);
}

// ---------------------------------------------------------------- team stats, last 10 minutes
function drawStats() {
  const r = stateAt(S.t), T = TXT[S.lang], st = T.stats;
  if (r.length < 14) { $('stats').hidden = $('stats-title').hidden = true; return; }
  const key = r.slice(6).join('|') + S.lang;
  if (key === drawStats.key) return;
  drawStats.key = key;
  // Each label links to its entry in the glossary (opens in a new tab, so the replay keeps running).
  const term = (label, id) => el('a', { href: `glossary.html#${id}`, target: '_blank', rel: 'noopener' }, label);
  const row = (label, h, a) => el('tr', {}, el('th', { scope: 'row' }, label), el('td', { class: 'home' }, h), el('td', { class: 'away' }, a));
  $('stats').replaceChildren(
    el('thead', {}, el('tr', {}, el('th', {}, ''), el('th', { scope: 'col' }, S.data.clubs.home), el('th', { scope: 'col' }, S.data.clubs.away))),
    el('tbody', {}, row(term(st.tilt, 'field-tilt'), `${pct(r[6])}%`, `${pct(r[7])}%`), row(term(st.ppda, 'ppda'), num1(r[8]), num1(r[9])),
      row(term(st.duels, 'duels'), `${pct(r[10])}%`, `${pct(r[11])}%`), row(term(st.xg, 'xg'), num2(r[12]), num2(r[13]))));
}

// ---------------------------------------------------------------- full time: the match report
// Made from the match file alone (timeline, comments, dead-ball cards), so it works for any
// narrated match. Shown at 90 minutes; scrubbing back hides it.
function matchSummary() {
  const D = S.data, types = D.timeline.event_types, t = () => ({ shots: 0, sot: 0, passes: 0, ok: 0, duels: 0, corners: 0, fouls: 0, yellow: 0, red: 0, offsides: 0 });
  const st = { home: t(), away: t() }, goals = [];
  let duelsAll = 0;
  for (const e of D.timeline.events) {
    const type = types[e[1]], side = e[2] === 0 ? 'home' : 'away', x = st[side];
    if (type === 'shot') { x.shots++; if (e[7] === 'goal' || e[7] === 'saved') x.sot++; if (e[7] === 'goal') goals.push({ t: e[0], player: e[8], team: side }); }
    else if (type === 'pass') { x.passes++; if (e[7] === 'success') x.ok++; }
    else if (type === 'duel') { x.duels++; duelsAll++; }
    else if (type === 'restart' && e[10] === 'corner') x.corners++;
    else if (type === 'foul') { x.fouls++; if (e[10] === 'yellow') x.yellow++; if (e[10] === 'red') x.red++; }
    else if (type === 'offside') x.offsides++;
  }
  const last = D.timeline.series[D.timeline.series.length - 1];
  const swings = goals.map((g) => {
    const before = stateAt(g.t - 0.05), after = D.timeline.series.find((r) => r[0] >= g.t) || last;
    const idx = g.team === 'home' ? 1 : null, val = (r) => (idx ? r[1] : Math.max(0, 1 - r[1] - r[2]));
    return { ...g, a: val(before), b: val(after) };
  }).sort((p, q) => Math.abs(q.b - q.a) - Math.abs(p.b - p.a)).slice(0, 3);
  const finds = (D.deadball || []).filter((c) => c.finding && c.finding.significant).map((c) => c.finding).sort((p, q) => p.p - q.p);
  return { st, goals, duelsAll, last, swings, finding: finds[0] || null };
}
function drawFulltime() {
  const end = S.t >= 5400 - 0.5, box = $('ft'), banner = $('ft-banner');
  if (!end) { if (!box.hidden) { box.hidden = true; banner.hidden = true; } box.dataset.key = ''; return; }
  const key = S.lang;
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  const D = S.data, T = TXT[S.lang], F = T.ft, sm = matchSummary(), H = D.clubs.home, A = D.clubs.away;
  const sh = sm.last[4], sa = sm.last[5];
  const htRow = stateAt(2699.9);
  const rate = (k, n) => (n ? `${Math.round(100 * k / n)}%` : '-');
  const xg = (side) => (sm.last.length > 13 ? num2(sm.last[side === 'home' ? 12 : 13]) : '-');
  const row = (label, h, a) => el('tr', {}, el('th', { scope: 'row' }, label), el('td', { class: 'home' }, String(h)), el('td', { class: 'away' }, String(a)));
  const R = F.rows, h = sm.st.home, a = sm.st.away;
  const stats = el('table', {}, el('thead', {}, el('tr', {}, el('th', {}, ''), el('th', { scope: 'col' }, H), el('th', { scope: 'col' }, A))),
    el('tbody', {}, row(R.shots, h.shots, a.shots), row(R.sot, h.sot, a.sot), row(R.xg, xg('home'), xg('away')),
      row(R.passes, h.passes, a.passes), row(R.comp, rate(h.ok, h.passes), rate(a.ok, a.passes)),
      row(R.duels, rate(h.duels, sm.duelsAll), rate(a.duels, sm.duelsAll)), row(R.corners, h.corners, a.corners),
      row(R.fouls, h.fouls, a.fouls), row(R.yellow, h.yellow, a.yellow), row(R.red, h.red, a.red), row(R.offsides, h.offsides, a.offsides)));
  const goalList = sm.goals.length ? el('ul', {}, sm.goals.map((g) => el('li', {}, el('span', { class: 'm' }, minLabel(g.t)),
    el('i', { class: `kit ${g.team}`, 'aria-hidden': 'true' }), ' ', `${who(g.player)}, ${D.clubs[g.team]}`))) : el('p', {}, F.none);
  const story = [el('h3', {}, F.story)];
  if (D.pre_match) { const [ph, pd, pa] = D.pre_match.map((v) => Math.round(v * 100)); story.push(el('p', {}, F.pre(H, ph, pd, A, pa))); }
  story.push(el('p', {}, sh > sa ? F.result.home(H) : sa > sh ? F.result.away(A) : F.result.draw()));
  if (sm.swings.length) {
    story.push(el('h3', {}, F.swingsTitle));
    story.push(el('ul', {}, sm.swings.map((g) => el('li', {}, F.swing(minLabel(g.t), who(g.player), D.clubs[g.team], Math.round(g.a * 100), Math.round(g.b * 100))))));
  }
  if (sm.finding) {
    const f = sm.finding, rt = F.rateText[f.metric];
    const text = `${D.clubs[f.team]} ${f.metric === 'shots' ? rt(f.now_k) : rt(f.now_k, f.now_n, Math.round(f.before_rate * 100))}.`;
    story.push(el('p', {}, F.finding(minLabel(f.t), text)));
  }
  // Count each comment once, in the language on screen (as the fact-check panel does).
  const langs = new Set(D.comments.map((c) => c.output.language));
  const all = D.comments.map((c) => c.output).filter((o) => !langs.has(S.lang) || o.language === S.lang);
  const n = (k) => all.filter((o) => o.status === k).length;
  story.push(el('h3', {}, F.checks), el('p', {}, F.checkLine(all.length, n('verified'), n('verified_on_retry'), n('fallback'), (D.stopped || []).filter((x) => !langs.has(S.lang) || x.language === S.lang).length)));
  if (D.history) story.push(el('h3', {}, F.copied), el('p', {}, F.copiedLine(D.history.season, D.history.date)));
  // The notice: large, above the pitch. The pitch, the scrubber and every view stay as they are.
  banner.replaceChildren(el('span', { class: 'notice' }, F.title),
    el('span', { class: 'line' }, el('span', { class: 'club home' }, el('i', { class: 'kit', 'aria-hidden': 'true' }), ' ', H),
      el('span', { class: 'goals' }, String(sh)), el('span', { class: 'goals' }, String(sa)),
      el('span', { class: 'club away' }, A, ' ', el('i', { class: 'kit', 'aria-hidden': 'true' })), el('span', { class: 'ht' }, F.ht(htRow[4], htRow[5]))),
    el('span', { class: 'acts' },
      el('button', { type: 'button', class: 'btn', onclick: () => { S.t = 0; S.shown.clear(); S.goalsSaid.clear(); setPlaying(true); } }, F.again),
      el('button', { type: 'button', class: 'btn', onclick: () => { const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches; box.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }); } }, F.toReport)));
  banner.hidden = false;
  // The report: under the pitch, above the log.
  box.replaceChildren(el('h2', { id: 'ft-title' }, F.report),
    el('div', { class: 'cols' }, el('div', {}, el('h3', {}, F.goals), goalList), el('div', {}, el('h3', {}, F.stats), stats), el('div', { class: 'story' }, ...story)));
  box.hidden = false;
}

// ---------------------------------------------------------------- zoom into the pitch
// The pitch is an SVG, so zoom changes its viewBox: everything stays sharp, and the shirt numbers
// grow with it. Buttons: +, -, Whole pitch, Follow the ball. Drag to move a zoomed pitch;
// the mouse wheel (or a trackpad pinch) zooms where the pointer is. The page opens at 1x.
const VB = { x: -2, y: -3.2, w: 109, h: 76.6 }, ZOOMS = [1, 1.5, 2, 3, 4];
const Z = { level: 1, cx: VB.x + VB.w / 2, cy: VB.y + VB.h / 2, follow: true, drag: null, key: '' };
function focusPoint() {
  if (S.trackState === 'ready' && (S.view === 'players' || S.view === 'running')) {
    const T = S.track, n = T.frames.length - 1, f0 = Math.min(n, Math.floor(S.t)), f1 = Math.min(n, f0 + 1), a = S.t - f0;
    const bx = (T.frames[f0][0] + (T.frames[f1][0] - T.frames[f0][0]) * a) / 10, by = (T.frames[f0][1] + (T.frames[f1][1] - T.frames[f0][1]) * a) / 10;
    return [MX(bx, S.t), MY(by, S.t)];
  }
  const i = lastEventIndex(S.t);
  if (i < 0) return [52.5, 34];
  const r = S.data.timeline.events[i];
  return [MX(r[5] ?? r[3], r[0]), MY(r[6] ?? r[4], r[0])];
}
function setZoom(level, about) {
  const old = Z.level;
  Z.level = Math.max(1, Math.min(4, level));
  if (about && Z.level !== old) {                    // keep the point under the pointer where it is
    const k = old / Z.level;
    Z.cx = about[0] + (Z.cx - about[0]) * k; Z.cy = about[1] + (Z.cy - about[1]) * k;
  }
  $('zoom-in').disabled = Z.level >= 4; $('zoom-out').disabled = Z.level <= 1; $('zoom-fit').disabled = Z.level <= 1;
  $('pitch').parentElement.classList.toggle('zoomed', Z.level > 1);
}
function applyZoom() {
  if (!S.data) return;
  if (Z.level > 1 && Z.follow && !Z.drag) {            // ease toward the ball, so the view does not jump
    const [fx, fy] = focusPoint();
    Z.cx += (fx - Z.cx) * 0.12; Z.cy += (fy - Z.cy) * 0.12;
  }
  const w = VB.w / Z.level, h = VB.h / Z.level;
  Z.cx = Math.max(VB.x + w / 2, Math.min(VB.x + VB.w - w / 2, Z.cx));
  Z.cy = Math.max(VB.y + h / 2, Math.min(VB.y + VB.h - h / 2, Z.cy));
  const vb = Z.level === 1 ? `${VB.x} ${VB.y} ${VB.w} ${VB.h}` : `${(Z.cx - w / 2).toFixed(2)} ${(Z.cy - h / 2).toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`;
  if (vb !== Z.key) { Z.key = vb; $('pitch').setAttribute('viewBox', vb); }
}
function svgPoint(e) {
  const r = $('pitch').getBoundingClientRect(), w = VB.w / Z.level, h = VB.h / Z.level;
  return [Z.cx - w / 2 + ((e.clientX - r.left) / r.width) * w, Z.cy - h / 2 + ((e.clientY - r.top) / r.height) * h];
}
const nextZoom = (dir) => (dir > 0 ? ZOOMS.find((z) => z > Z.level + 1e-6) || 4 : [...ZOOMS].reverse().find((z) => z < Z.level - 1e-6) || 1);
$('zoom-in').addEventListener('click', () => { if (Z.level === 1) [Z.cx, Z.cy] = focusPoint(); setZoom(nextZoom(1)); });
$('zoom-out').addEventListener('click', () => setZoom(nextZoom(-1)));
$('zoom-fit').addEventListener('click', () => setZoom(1));
$('zoom-follow').addEventListener('click', () => { Z.follow = !Z.follow; $('zoom-follow').setAttribute('aria-pressed', String(Z.follow)); });
// The mouse wheel over the pitch zooms in and out around the point under the pointer. While the
// pointer is over the pitch, the wheel never scrolls the page (also at 1x and at 4x).
$('pitch').addEventListener('wheel', (e) => {
  e.preventDefault();
  const zoomIn = e.deltaY < 0;
  if ((!zoomIn && Z.level <= 1) || (zoomIn && Z.level >= 4)) return;
  if (Z.follow && zoomIn) { Z.follow = false; $('zoom-follow').setAttribute('aria-pressed', 'false'); }   // stay where the pointer is
  setZoom(Z.level * (zoomIn ? 1.2 : 1 / 1.2), svgPoint(e));
}, { passive: false });
// Hover: the player (or official) nearest the pointer, within 3 m, gets a label with his name,
// number, position, club and speed this second. It does not depend on which mark is on top.
function hoverTargets() {
  if ((S.view === 'players' || S.view === 'running') && playersLayer) return playersLayer.hits || [];
  if (S.view === 'shape' && shapeLayer) return shapeLayer.hits || [];
  return [];
}
// The label sticks to the player it found: while the replay plays, it moves with him, until the
// pointer moves away (over 8 m from him) or leaves the pitch.
const HOVER = { pt: null, id: null };
function showTip(e, fromFrame) {
  const tip = $('pitch-tip');
  if (Z.drag || !e) { tip.hidden = true; return; }
  const [px, py] = svgPoint(e), hits = hoverTargets();
  let best = null;
  if (HOVER.id != null) {                            // keep following him; a pointer move far away lets go
    best = hits.find((h) => h.id === HOVER.id) || null;
    if (best && !fromFrame && Math.hypot(best.x - px, best.y - py) > 8) best = null;
  }
  if (!best) {
    let bd = 3;
    for (const h of hits) { const d = Math.hypot(h.x - px, h.y - py); if (d < bd) { bd = d; best = h; } }
  }
  HOVER.id = best ? best.id : null;
  if (!best) { tip.hidden = true; return; }
  // Place it at the player (converted from pitch metres to the page), so it follows him.
  const r = $('pitch').getBoundingClientRect(), box = $('pitch').parentElement.getBoundingClientRect();
  const w = VB.w / Z.level, h = VB.h / Z.level, x0 = Z.level === 1 ? VB.x : Z.cx - w / 2, y0 = Z.level === 1 ? VB.y : Z.cy - h / 2;
  const sx = r.left + ((best.x - x0) / w) * r.width, sy = r.top + ((best.y - y0) / h) * r.height;
  if (tip.textContent !== best.text) tip.textContent = best.text;
  tip.hidden = false; tip.style.left = `${sx - box.left}px`; tip.style.top = `${sy - box.top}px`;
}
$('pitch').addEventListener('pointermove', (e) => { HOVER.pt = { clientX: e.clientX, clientY: e.clientY }; showTip(HOVER.pt, false); });
$('pitch').addEventListener('pointerleave', () => { HOVER.pt = null; HOVER.id = null; $('pitch-tip').hidden = true; });
// A click (not a drag) on a player or an official opens the camera from his eyes (cam.js).
let CLICK0 = null;
$('pitch').addEventListener('pointerdown', (e) => { CLICK0 = { x: e.clientX, y: e.clientY }; });
$('pitch').addEventListener('click', (e) => {
  const moved = CLICK0 ? Math.hypot(e.clientX - CLICK0.x, e.clientY - CLICK0.y) : 0;
  if (moved < 5 && HOVER.id && CAM && (S.view === 'players' || S.view === 'running')) CAM.open(HOVER.id);
});
$('pitch').addEventListener('pointerdown', (e) => {
  if (Z.level <= 1) return;
  Z.drag = { x: e.clientX, y: e.clientY, cx: Z.cx, cy: Z.cy };
  $('pitch').setPointerCapture(e.pointerId); $('pitch').parentElement.classList.add('dragging');
});
$('pitch').addEventListener('pointermove', (e) => {
  if (!Z.drag) return;
  const r = $('pitch').getBoundingClientRect(), k = (VB.w / Z.level) / r.width;
  Z.cx = Z.drag.cx - (e.clientX - Z.drag.x) * k; Z.cy = Z.drag.cy - (e.clientY - Z.drag.y) * k;
  if (Math.abs(e.clientX - Z.drag.x) + Math.abs(e.clientY - Z.drag.y) > 4 && Z.follow) {   // moving by hand stops following
    Z.follow = false; $('zoom-follow').setAttribute('aria-pressed', 'false');
  }
});
const endDrag = () => { Z.drag = null; $('pitch').parentElement.classList.remove('dragging'); };
$('pitch').addEventListener('pointerup', endDrag); $('pitch').addEventListener('pointercancel', endDrag);
function zoomWords() {
  const T = TXT[S.lang].zoom;
  $('zoom-in').setAttribute('aria-label', T.in); $('zoom-out').setAttribute('aria-label', T.out);
  $('zoom-fit').textContent = T.fit; $('zoom-follow').textContent = T.follow;
  $('zoom-in').title = T.in; $('zoom-out').title = T.out;
}

// A minute in the log: stop, go to that moment, show everyone.
function showMoment(t) {
  setPlaying(false); S.t = t; setView('players');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  $('pitch').scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
}

// ---------------------------------------------------------------- the log
function personaLabel(id) {
  const T = TXT[S.lang], p = S.data.personas.find((x) => x.persona_id === id) || {};
  if (id === 'analyst') return T.analyst;
  if (p.favorite_team) return T.fan(S.data.clubs[p.favorite_team]);
  if (p.favorite_player) return T.follow(who((S.data.players || {})[p.favorite_player] || p.favorite_player));
  return id;
}
function buildHead() {
  const T = TXT[S.lang], table = $('log');
  table.querySelector('colgroup')?.remove();
  table.insertBefore(el('colgroup', {}, el('col', { class: 'c-min' }), el('col', { class: 'c-moment' }),
    S.data.personas.map(() => el('col', {}))), table.tHead);
  $('log-head').replaceChildren(el('th', { scope: 'col' }, T.min), el('th', { scope: 'col' }, T.moment),
    ...S.data.personas.map((p) => el('th', { scope: 'col' }, personaLabel(p.persona_id))));
  $('log-caption').textContent = T.caption;
}
function cell(m, pid) {
  const slot = m.by[pid], label = personaLabel(pid);
  if (!slot || slot.air > S.t) return el('td', { class: 'cell quiet', 'data-label': label }, el('span', { class: 'sr-only' }, TXT[S.lang].noComment));
  const o = pick(slot).output, T = TXT[S.lang];
  const btn = el('button', { type: 'button', class: `say s-${o.status}`, onclick: () => openDrawer(m, pid) },
    o.text, o.status === 'verified' ? el('span', { class: 'sr-only' }, `. ${T.status.verified}`) : el('span', { class: 'mark' }, T.status[o.status]));
  return el('td', { class: 'cell', 'data-label': label }, btn);
}
let lastKey = '';
function drawLog(force) {
  const visible = S.data.moments.filter((m) => m.first <= S.t);
  // A row changes when a moment appears or a late comment (after a cooldown) airs in it.
  const key = visible.map((m) => m.id + Object.values(m.by).filter((s) => s.air <= S.t).length).join(',') + S.lang;
  if (!force && key === lastKey) return;
  lastKey = key;
  const rows = visible.slice().reverse().map((m) => {
    const d = describe(m.id), isNew = S.playing && !S.shown.has(m.id);
    S.shown.add(m.id);
    if (m.goal && S.playing && !S.goalsSaid.has(m.id)) { S.goalsSaid.add(m.id); $('announce').textContent = TXT[S.lang].goalSaid(S.data.clubs[d.team], minLabel(m.at)); }
    return el('tr', { class: [m.goal ? 'goal' : '', isNew ? 'new' : ''].join(' ').trim() || null },
      el('td', { class: 'min' }, el('button', { type: 'button', class: 'jump', 'aria-label': TXT[S.lang].jump(minLabel(m.at)), onclick: () => showMoment(m.at) }, minLabel(m.at))),
      el('td', { class: 'moment' }, el('span', { class: 'what' }, d.team ? el('i', { class: `kit ${d.team}`, 'aria-hidden': 'true' }) : null, d.what),
        el('span', { class: 'who' }, d.who)),
      ...S.data.personas.map((p) => cell(m, p.persona_id)));
  });
  $('log-body').replaceChildren(...(rows.length ? rows : [el('tr', {}, el('td', { class: 'empty-log', colspan: 2 + S.data.personas.length }, TXT[S.lang].empty))]));
}

// ---------------------------------------------------------------- the drawer: why trust it
function textWithClaims(o) {
  const p = el('p'); const parts = [];
  const claims = o.evidence.filter((e) => e.claim && o.text.includes(e.claim)).sort((a, b) => o.text.indexOf(a.claim) - o.text.indexOf(b.claim));
  let pos = 0;
  for (const e of claims) {
    const i = o.text.indexOf(e.claim, pos); if (i < 0) continue;
    if (i > pos) parts.push(o.text.slice(pos, i));
    parts.push(el('span', { class: 'claim' }, e.claim)); pos = i + e.claim.length;
  }
  parts.push(o.text.slice(pos)); p.append(...parts);
  return p;
}
let opener = null;
function openDrawer(m, pid) {
  const slot = m.by[pid], c = pick(slot), o = c.output, body = $('drawer-body'), es = S.lang === 'es', d = describe(m.id);
  const quote = textWithClaims(o); quote.className = 'quote';
  const kids = [el('h3', { id: 'drawer-title' }, `${personaLabel(pid)}, ${minLabel(slot.air)}`),
    el('p', { class: `status ${o.status}` }, `${TXT[S.lang].status[o.status]}. ${d.what}, ${d.who}.`), quote];
  const what = { verified: es ? 'El verificador comprobó cada dato a la primera.' : 'The verifier checked every fact on the first try.',
    verified_on_retry: es ? 'El primer borrador falló; el agente lo corrigió con la lista de fallos.' : 'The first draft failed. The agent fixed it from the list of failures.',
    fallback: es ? 'El agente falló dos veces: salió una frase de plantilla, rellenada solo con datos guardados.' : 'The agent failed twice. A template sentence aired instead, filled only from stored data.' };
  kids.push(el('p', { class: 'note' }, what[o.status] || ''));
  kids.push(el('h4', {}, es ? 'Cada dato y su fuente' : 'Every fact and its source'));
  const tb = el('tbody');
  for (const e of o.evidence) tb.append(el('tr', {}, el('td', {}, e.claim), el('td', { class: 'mono' }, e.source), el('td', { class: 'mono' }, String(e.value)), el('td', { class: 'ok' }, es ? 'comprobado' : 'checked')));
  kids.push(el('table', { class: 'ev' }, el('thead', {}, el('tr', {}, el('th', { text: es ? 'Dato' : 'Claim' }), el('th', { text: es ? 'Fuente' : 'Source' }), el('th', { text: es ? 'Valor guardado' : 'Stored value' }), el('th', {}, el('span', { class: 'sr-only' }, es ? 'Resultado' : 'Result')))), tb));
  const stopped = c.tries.filter((t) => !t.passed);
  if (stopped.length) {
    kids.push(el('h4', {}, es ? 'Lo que paró el verificador' : 'What the verifier stopped'));
    for (const t of stopped) kids.push(el('div', { class: 'stopped' }, el('p', {}, (t.draft && t.draft.text) || (es ? '(respuesta ilegible)' : '(unreadable answer)')),
      el('ul', {}, t.failures.map((f) => el('li', {}, `${f.check}: ${f.detail}`)))));
  }
  if (c.tool_calls && c.tool_calls.length) {
    kids.push(el('h4', {}, es ? 'Herramientas que usó el agente' : 'Tools the agent called'));
    kids.push(el('ul', { class: 'calls' }, c.tool_calls.map((x) => el('li', {}, el('b', {}, x.tool), ' ', JSON.stringify(x.args)))));
  }
  if (slot.at !== slot.air) kids.push(el('p', { class: 'note' }, es ? `Momento a los ${minLabel(slot.at)}; salió al terminar la pausa de 20 s de este espectador.` : `The moment was at ${minLabel(slot.at)}. It aired when this viewer's 20 s pause ended.`));
  body.replaceChildren(...kids);
  opener = document.activeElement;
  $('drawer').hidden = false; $('drawer-close').focus();
}
// Close returns focus to the comment that opened the drawer (or to the log if that row was redrawn).
function closeDrawer() {
  if ($('drawer').hidden) return;
  $('drawer').hidden = true;
  if (opener && opener.isConnected) opener.focus(); else document.querySelector('.say')?.focus();
}
$('drawer-close').addEventListener('click', closeDrawer);
$('drawer').addEventListener('click', (e) => { if (e.target.id === 'drawer') closeDrawer(); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeDrawer();
  if (e.key === 'Tab' && !$('drawer').hidden) {   // keep Tab inside the open dialog
    const f = [...$('drawer').querySelectorAll('button,[href],[tabindex]:not([tabindex="-1"])')];
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  }
});

// The player camera (cam.js): a 3D view from one player's eyes, in step with the replay.
const CAM = window.makeCam ? window.makeCam({ S, $, TXT, cssColor, ballZ, offPitch, OFFICIAL_MARK }) : null;

// ---------------------------------------------------------------- replay
function frame(now) {
  if (S.replay) {                                    // a key moment playing its lead-up
    // Play, the scrubber, the chart or "Next goal" moved the clock: the replay stops there.
    if (S.playing || (S.replay.last != null && Math.abs(S.t - S.replay.last) > 0.01)) S.replay = null;
    else {
      S.t = Math.min(S.replay.to, S.t + Math.min(0.25, (now - S.last) / 1000) * REPLAY_SPEED);
      S.replay.last = S.t;
      if (S.t >= S.replay.to) { const r = S.replay; S.replay = null; if (r.onEnd) r.onEnd(); }
    }
  }
  if (S.playing) {
    const dt = Math.min(0.25, (now - S.last) / 1000);
    S.t = Math.min(5400, S.t + dt * S.speed);
    if (S.t >= 5400) setPlaying(false);
  }
  S.last = now;
  S.edge = Math.max(S.edge || 0, S.t);               // the live edge (key moments)
  drawBoard(); drawChart(); drawPitch(); applyZoom(); if (HOVER.pt) showTip(HOVER.pt, true);
  if (CAM) { CAM.words(); CAM.frame(); } drawLog(false); drawDead(now); drawStats(); drawFulltime();
  if (S.data && !$('through-controls').hidden) momentsMenu();
  requestAnimationFrame(frame);
}
function setPlaying(on) { S.playing = on; $('play').textContent = on ? TXT[S.lang].pause : TXT[S.lang].play; }
$('play').addEventListener('click', () => { if (S.t >= 5400) { S.t = 0; S.shown.clear(); S.goalsSaid.clear(); } setPlaying(!S.playing); });
// Speeds: 1x is real time (one match minute takes one minute), up to 120x (the match in 45 s).
$('speed').addEventListener('change', (e) => { S.speed = +e.target.value; });
$('scrub').addEventListener('input', (e) => { S.t = +e.target.value; });
$('next-goal').addEventListener('click', () => {
  const g = S.data.timeline.notable.find((n) => n.goal && n.t > S.t + 1);
  if (g) S.t = g.t + 1;
});
function applyLanguage() {
  const T = TXT[S.lang];
  document.documentElement.lang = S.lang;
  $('speed-label').textContent = T.speed; $('speed').options[0].textContent = T.realTime; $('next-goal').textContent = T.nextGoal; $('drawer-close').textContent = T.close;
  $('scrub').setAttribute('aria-label', T.scrub); $('win-title').textContent = T.win; $('checks-title').textContent = T.checks;
  $('foot').textContent = T.foot; $('gloss-link').textContent = T.gloss; helpWords();
  setPlaying(S.playing);
  viewButtons();
  if (S.data) { drawBoard.wkey = drawBoard.ckey = null; drawStats.key = null; $('dead').dataset.key = ''; $('ft').dataset.key = ''; buildPitch(); buildHead(); drawLog(true); sourceLines(); }
  $('stats-title').textContent = T.statsTitle; kitWords(); zoomWords();
  if (S.trackState === 'ready') fillHeatPlayers();
}
document.querySelectorAll('.lang button').forEach((b) => b.addEventListener('click', () => {
  S.lang = b.dataset.lang;
  document.querySelectorAll('.lang button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  applyLanguage();
}));

// ---------------------------------------------------------------- help for viewers (2026-10-27)
// "How to use this page": open on the first visit, closed after the viewer closes it once (kept in
// this browser). Short hints sit next to the pitch, the key moments, the chart and the log.
function helpWords() {
  const H = TXT[S.lang].help, hints = TXT[S.lang].hints;
  $('help-title').textContent = H.title; $('help-link').textContent = H.link;
  $('help-body').replaceChildren(el('p', { class: 'help-intro' }, H.intro),
    el('div', { class: 'help-cols' }, ...H.sections.map(([h, items]) =>
      el('section', {}, el('h3', {}, h), el('ul', {}, ...items.map((t) => el('li', {}, t)))))));
  $('pitch-hint').textContent = hints.pitch; $('km-hint').textContent = hints.km;
  $('chart-hint').textContent = hints.chart; $('log-hint').textContent = hints.log;
}
try { if (localStorage.getItem('sixth.help') === 'closed') $('help').open = false; } catch (e) { /* default: open */ }
$('help').addEventListener('toggle', () => { try { localStorage.setItem('sixth.help', $('help').open ? 'open' : 'closed'); } catch (e) { /* not kept */ } });
$('help-link').addEventListener('click', (e) => { e.preventDefault(); $('help').open = true; $('help').scrollIntoView({ block: 'start' }); $('help').querySelector('summary').focus(); });

function sourceLines() {
  const d = S.data, T = TXT[S.lang];
  const by = d.narrator === 'foundry' ? `Commentary by ${d.model || 'a Microsoft Foundry model'} through Microsoft Agent Framework` : 'Commentary by the rule-based template narrator (no model)';
  $('source').textContent = `${by}. Match seed ${d.seed}. Each comment was checked against the match data before it aired.` + (d.history ? ' ' + T.history(d.history.season, d.history.date) : '');
  if (d.pre_match) {
    const [h, dr, a] = d.pre_match.map(pct);
    $('pre').textContent = T.pre(d.clubs.home, h, dr, d.clubs.away, a);
  }
}
$('flip').addEventListener('change', (e) => { S.flip = e.target.checked; if (playersLayer) playersLayer.note = ''; if (heatLayer) heatLayer.key = ''; if (shapeLayer) shapeLayer.key = ''; });
loadKits();
load().then((d) => {
  S.data = d;
  $('home-name').textContent = d.clubs.home; $('away-name').textContent = d.clubs.away;
  sourceLines(); kitWords();
  buildChart(); buildPitch(); buildHead(); viewButtons(); helpWords();
  for (const id of ['play', 'speed', 'scrub']) $(id).disabled = false;   // enabled once the match is loaded
  if (S.view !== 'play') loadTracking();             // the page opens on All players (2026-10-27)
  requestAnimationFrame((n) => { S.last = n; frame(n); });
}).catch((e) => { $('source').textContent = `The match could not be loaded: ${e.message}`; });
})();
