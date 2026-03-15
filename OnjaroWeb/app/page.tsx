export default function HomePage() {
  const categories = [
    {
      icon: "🚴",
      title: "Országúti Kerékpározás",
      description:
        "Tippek, útvonalak és edzéstervek az aszfalton. Teljesítményoptimalizálás 45+ felett.",
      tag: "Road Bike",
    },
    {
      icon: "⛰️",
      title: "Mountain Bike (MTB)",
      description:
        "Terepen, hegyeken, erdőkben. Technika, biztonság és a természet szeretete.",
      tag: "MTB",
    },
    {
      icon: "🌿",
      title: "Ciklokrossz",
      description:
        "A cyclocross izgalma: őszi sár, akadályok, erő és ügyesség egyszerre.",
      tag: "CX",
    },
  ];

  const features = [
    {
      icon: "💪",
      title: "Korosztály-specifikus edzéstervek",
      description:
        "45-60 éves korban a regeneráció és az ízületek védelme kulcskérdés. Terveinket erre szabtuk.",
    },
    {
      icon: "🛠️",
      title: "Felszerelés-tanácsok",
      description:
        "Prémium kerékpáros felszerelések objektív tesztelése és összehasonlítása tapasztalt szemmel.",
    },
    {
      icon: "🏅",
      title: "Teljesítményoptimalizálás",
      description:
        "Hogyan lehetsz jobb kerékpáros életkorod ellenére? Tudományos alapú, praktikus tanácsok.",
    },
    {
      icon: "⏱️",
      title: "Időbeosztás segítség",
      description:
        "Munka, család és kerékpározás egyensúlya. Hatékony edzésprogramok elfoglalt embereknek.",
    },
  ];

  const articles = [
    {
      category: "Edzésterv",
      title: "Alapfitnesz felépítése 50 felett: A 12 hetes terv",
      excerpt:
        "Ha újra nyeregbe szállsz vagy szintet akarsz lépni, ez a program a te kiindulópontod. Fokozatos terhelés, regenerációs napokkal.",
      readTime: "8 perc",
      tag: "Road Bike",
    },
    {
      category: "Felszerelés",
      title: "A legjobb elektromos MTB-k 2025-ben prémium kategóriában",
      excerpt:
        "Az e-bike nem csalás – erősíti a teljesítményed és tovább tart az élmény. Megnéztük, mi éri meg az árát.",
      readTime: "12 perc",
      tag: "MTB",
    },
    {
      category: "Egészség",
      title: "Térd- és csípővédelem kerékpározás közben",
      excerpt:
        "Az ízületi problémák nem kell, hogy véget vessenek a kerékpározásnak. Megelőzés, pozíció, erősítő gyakorlatok.",
      readTime: "6 perc",
      tag: "Egészség",
    },
  ];

  const tagColors: Record<string, string> = {
    "Road Bike": "bg-blue-100 text-blue-700",
    MTB: "bg-green-100 text-green-700",
    CX: "bg-orange-100 text-orange-700",
    Egészség: "bg-purple-100 text-purple-700",
    Edzésterv: "bg-cyan-100 text-cyan-700",
    Felszerelés: "bg-amber-100 text-amber-700",
  };

  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <span className="text-2xl">🚵</span>
              <span className="text-xl font-bold text-brand-700">Onjaro</span>
            </div>
            <div className="hidden md:flex items-center gap-6">
              <a
                href="#kategoriak"
                className="text-gray-600 hover:text-brand-600 font-medium transition-colors"
              >
                Kategóriák
              </a>
              <a
                href="#cikkek"
                className="text-gray-600 hover:text-brand-600 font-medium transition-colors"
              >
                Cikkek
              </a>
              <a
                href="#rolunk"
                className="text-gray-600 hover:text-brand-600 font-medium transition-colors"
              >
                Rólunk
              </a>
            </div>
            <button className="btn-primary text-sm py-2 px-4">
              Feliratkozás
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 text-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm rounded-full px-4 py-1.5 mb-6">
              <span className="text-sm font-medium text-blue-100">
                Magyar kerékpáros portál 45-60 éveseknek
              </span>
            </div>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight mb-6">
              Kerékpározz okosan,{" "}
              <span className="text-accent-400">élj teljesebben</span>
            </h1>
            <p className="text-lg md:text-xl text-blue-100 mb-8 leading-relaxed">
              Edzéstervek, felszerelés-tanácsok és tippek tapasztalt
              kerékpárosoknak. Mert a legjobb éveid még előtted állnak a
              nyergen.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <button className="bg-accent-500 hover:bg-accent-600 text-white px-8 py-4 rounded-lg font-semibold text-lg transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-accent-400 focus:ring-offset-2 focus:ring-offset-brand-700">
                Fedezd fel a tartalmakat
              </button>
              <button className="bg-white/10 hover:bg-white/20 text-white border border-white/30 px-8 py-4 rounded-lg font-semibold text-lg transition-colors duration-200">
                Edzéstervek →
              </button>
            </div>
          </div>
        </div>
        {/* Wave divider */}
        <div className="relative">
          <svg
            className="w-full h-12 text-gray-50 fill-current"
            viewBox="0 0 1200 48"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path d="M0,48 L0,24 Q300,0 600,24 T1200,24 L1200,48 Z" />
          </svg>
        </div>
      </section>

      {/* Stats bar */}
      <section className="bg-gray-50 border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            {[
              { value: "200+", label: "Szakmai cikk" },
              { value: "50+", label: "Edzésterv" },
              { value: "30+", label: "Felszerelés-teszt" },
              { value: "45-60", label: "Célkorosztály" },
            ].map((stat) => (
              <div key={stat.label}>
                <div className="text-3xl font-bold text-brand-700">
                  {stat.value}
                </div>
                <div className="text-gray-500 text-sm mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Categories */}
      <section id="kategoriak" className="py-16 bg-gray-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
              Válaszd a te útjadat
            </h2>
            <p className="text-gray-500 text-lg max-w-2xl mx-auto">
              Legyen szó aszfaltról, terepről vagy cross-pályáról – minden
              kerékpáros megtalálja a maga közösségét.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {categories.map((cat) => (
              <div
                key={cat.title}
                className="card cursor-pointer group hover:-translate-y-1 transition-transform duration-200"
              >
                <div className="text-5xl mb-4">{cat.icon}</div>
                <div className="mb-2">
                  <span
                    className={`text-xs font-semibold px-2 py-1 rounded-full ${tagColors[cat.tag] ?? "bg-gray-100 text-gray-600"}`}
                  >
                    {cat.tag}
                  </span>
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-2 group-hover:text-brand-700 transition-colors">
                  {cat.title}
                </h3>
                <p className="text-gray-500 leading-relaxed">{cat.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-16 bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
              Miért az Onjaro?
            </h2>
            <p className="text-gray-500 text-lg max-w-2xl mx-auto">
              Nem általános kerékpáros oldal. Az Onjaro kifejezetten a tapasztalt
              korosztály igényeire épül.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
            {features.map((feature) => (
              <div key={feature.title} className="flex gap-4">
                <div className="text-3xl flex-shrink-0">{feature.icon}</div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    {feature.title}
                  </h3>
                  <p className="text-gray-500 leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Latest Articles */}
      <section id="cikkek" className="py-16 bg-gray-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between mb-12">
            <div>
              <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
                Legújabb cikkek
              </h2>
              <p className="text-gray-500">Friss tartalmak tapasztalt kerékpárosoktól</p>
            </div>
            <button className="hidden md:block btn-secondary text-sm py-2">
              Összes cikk →
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {articles.map((article) => (
              <article
                key={article.title}
                className="card cursor-pointer group"
              >
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className={`text-xs font-semibold px-2 py-1 rounded-full ${tagColors[article.tag] ?? "bg-gray-100 text-gray-600"}`}
                  >
                    {article.tag}
                  </span>
                  <span className="text-xs text-gray-400">{article.category}</span>
                </div>
                <h3 className="text-lg font-bold text-gray-900 mb-3 group-hover:text-brand-700 transition-colors leading-snug">
                  {article.title}
                </h3>
                <p className="text-gray-500 text-sm leading-relaxed mb-4">
                  {article.excerpt}
                </p>
                <div className="flex items-center justify-between text-xs text-gray-400 border-t border-gray-100 pt-3">
                  <span>⏱️ {article.readTime} olvasás</span>
                  <span className="text-brand-600 font-medium group-hover:underline">
                    Olvasd el →
                  </span>
                </div>
              </article>
            ))}
          </div>
          <div className="text-center mt-8 md:hidden">
            <button className="btn-secondary">Összes cikk →</button>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section id="rolunk" className="py-16 bg-brand-700 text-white">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <span className="text-4xl mb-4 block">📬</span>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Ne maradj le semmiről!
          </h2>
          <p className="text-blue-100 text-lg mb-8 leading-relaxed">
            Iratkozz fel hírlevelünkre és elsőként értesülsz az új edzéstervekről,
            felszerelés-tesztekről és közösségi eseményekről.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto">
            <input
              type="email"
              placeholder="email@cimed.hu"
              className="flex-1 px-4 py-3 rounded-lg text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-400"
              aria-label="E-mail cím"
            />
            <button className="bg-accent-500 hover:bg-accent-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors whitespace-nowrap">
              Feliratkozás
            </button>
          </div>
          <p className="text-blue-200 text-xs mt-3">
            Spam-mentes. Bármikor leiratkozhatsz.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xl">🚵</span>
              <span className="text-white font-bold text-lg">Onjaro</span>
            </div>
            <p className="text-sm text-center">
              Magyar kerékpársport-portál 45-60 éves férfiak számára
            </p>
            <p className="text-sm">© 2026 Onjaro. Minden jog fenntartva.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
