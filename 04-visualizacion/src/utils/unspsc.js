// Segmentos UNSPSC (2 dígitos). dim_categoria de oro trae códigos sin nombres; la web los nombra aquí.
// "00" = sin categoría: desde mediados de septiembre de 2026 SECOP publica casi todos los procesos como UNSPECIFIED.
export const SEGMENTOS = {
  '10': ['Material vivo vegetal y animal', 'Material vivo vegetal y animal, accesorios y suministros'],
  '11': ['Minerales y textiles no comestibles', 'Material mineral, textil y vegetal y animal no comestible'],
  '12': ['Químicos', 'Material químico, incluidos bioquímicos y materiales de gas'],
  '13': ['Resinas, cauchos y espumas', 'Resinas, colofonias, cauchos, espumas, películas y materiales elastoméricos'],
  '14': ['Papel', 'Materiales y productos de papel'],
  '15': ['Combustibles y lubricantes', 'Combustibles, aditivos para combustibles, lubricantes y anticorrosivos'],
  '20': ['Maquinaria de minería', 'Maquinaria y accesorios de minería y perforación de pozos'],
  '21': ['Maquinaria agrícola', 'Maquinaria y accesorios para agricultura, pesca, silvicultura y fauna'],
  '22': ['Maquinaria de construcción', 'Maquinaria y accesorios para construcción y edificación'],
  '23': ['Maquinaria industrial', 'Maquinaria y accesorios para manufactura y procesamiento industrial'],
  '24': ['Manejo de materiales', 'Maquinaria, accesorios y suministros para manejo y almacenamiento de materiales'],
  '25': ['Vehículos y repuestos', 'Vehículos comerciales, militares y particulares, accesorios y componentes'],
  '26': ['Generación de energía', 'Maquinaria y accesorios para generación y distribución de energía'],
  '27': ['Herramientas', 'Herramientas y maquinaria general'],
  '30': ['Materiales de construcción', 'Componentes y suministros para estructuras, edificación, construcción y obras civiles'],
  '31': ['Componentes de manufactura', 'Componentes y suministros de manufactura'],
  '32': ['Componentes electrónicos', 'Componentes y suministros electrónicos'],
  '39': ['Sistemas eléctricos e iluminación', 'Componentes, accesorios y suministros de sistemas eléctricos e iluminación'],
  '40': ['Climatización y distribución', 'Componentes y equipos para distribución y sistemas de acondicionamiento'],
  '41': ['Equipos de laboratorio', 'Equipos y suministros de laboratorio, de medición, de observación y de pruebas'],
  '42': ['Equipo médico', 'Equipo médico, accesorios y suministros'],
  '43': ['Tecnología y telecomunicaciones', 'Difusión de tecnologías de información y telecomunicaciones'],
  '44': ['Equipos de oficina', 'Equipos de oficina, accesorios y suministros'],
  '45': ['Impresión y audiovisuales', 'Equipos y suministros para impresión, fotografía y audiovisuales'],
  '46': ['Defensa y seguridad (equipos)', 'Equipos y suministros de defensa, orden público, protección, vigilancia y seguridad'],
  '47': ['Equipos de limpieza', 'Equipos de limpieza y suministros'],
  '48': ['Equipo para servicios', 'Maquinaria, equipo y suministros para la industria de servicios'],
  '49': ['Deportes y recreación', 'Equipos, suministros y accesorios para deportes y recreación'],
  '50': ['Alimentos y bebidas', 'Alimentos, bebidas y tabaco'],
  '51': ['Medicamentos', 'Medicamentos y productos farmacéuticos'],
  '52': ['Artículos domésticos', 'Artículos domésticos, suministros y productos electrónicos de consumo'],
  '53': ['Ropa y aseo personal', 'Ropa, maletas y productos de aseo personal'],
  '54': ['Relojería y joyería', 'Productos para relojería, joyería y piedras preciosas'],
  '55': ['Publicaciones', 'Publicaciones impresas, publicaciones electrónicas y accesorios'],
  '56': ['Muebles', 'Muebles, mobiliario y decoración'],
  '60': ['Material educativo y artes', 'Instrumentos musicales, juegos, artes, artesanías y equipo educativo'],
  '64': ['Instrumentos financieros', 'Instrumentos financieros, productos y accesorios'],
  '70': ['Servicios agrícolas', 'Servicios de contratación agrícola, pesquera, forestal y de fauna'],
  '71': ['Servicios de minería y petróleo', 'Servicios de minería, petróleo y gas'],
  '72': ['Construcción y mantenimiento', 'Servicios de edificación, construcción de instalaciones y mantenimiento'],
  '73': ['Producción industrial', 'Servicios de producción industrial y manufactura'],
  '76': ['Limpieza y residuos', 'Servicios de limpieza, descontaminación y tratamiento de residuos'],
  '77': ['Servicios medioambientales', 'Servicios medioambientales'],
  '78': ['Transporte y almacenaje', 'Servicios de transporte, almacenaje y correo'],
  '80': ['Gestión y servicios profesionales', 'Servicios de gestión, servicios profesionales de empresa y servicios administrativos'],
  '81': ['Ingeniería e investigación', 'Servicios basados en ingeniería, investigación y tecnología'],
  '82': ['Diseño y artes gráficas', 'Servicios editoriales, de diseño, de artes gráficas y bellas artes'],
  '83': ['Servicios públicos', 'Servicios públicos y servicios relacionados con el sector público'],
  '84': ['Financieros y seguros', 'Servicios financieros y de seguros'],
  '85': ['Salud', 'Servicios de salud'],
  '86': ['Educación y formación', 'Servicios educativos y de formación'],
  '90': ['Viajes, alimentación y eventos', 'Servicios de viajes, alimentación, alojamiento y entretenimiento'],
  '91': ['Servicios personales', 'Servicios personales y domésticos'],
  '92': ['Seguridad y vigilancia', 'Servicios de defensa nacional, orden público, seguridad y vigilancia'],
  '93': ['Asuntos cívicos', 'Servicios políticos y de asuntos cívicos'],
  '94': ['Organizaciones y clubes', 'Organizaciones y clubes'],
  '95': ['Terrenos y edificios', 'Terrenos, edificios, estructuras y vías'],
  '00': ['Sin categoría', 'Sin categoría publicada en SECOP'],
}

export function nombreSegmento(codigo, largo = false) {
  const c = String(codigo ?? '').padStart(2, '0').slice(0, 2)
  const s = SEGMENTOS[c]
  if (!s) return `Segmento ${c}`
  return largo ? s[1] : s[0]
}

export const SEGMENTOS_ORDENADOS = Object.entries(SEGMENTOS)
  .filter(([c]) => c !== '00')
  .map(([codigo, [corto, largo]]) => ({ codigo, corto, largo }))
  .sort((a, b) => a.corto.localeCompare(b.corto, 'es'))
