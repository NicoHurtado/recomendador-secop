-- Capa plata · tablas Iceberg (válidos y rechazados por tabla)

CREATE TABLE secop_silver.procesos (
  id_proceso string COMMENT 'Llave del proceso CO1.REQ. Llave del MERGE',
  id_portafolio string COMMENT 'CO1.BDOS. Cruce con contratos.proceso_de_compra',
  referencia_proceso string,
  nit_entidad string COMMENT 'NIT normalizado: solo dígitos, sin DV',
  nombre_entidad string,
  departamento_entidad string,
  ciudad_entidad string,
  orden_entidad string,
  modalidad string COMMENT 'Una de las 10 modalidades del alcance',
  tipo_contrato string,
  descripcion string COMMENT 'Texto original',
  descripcion_limpia string COMMENT 'Minúsculas, sin tildes ni caracteres especiales',
  precio_base decimal(18, 2) COMMENT 'Valores menores o iguales a 0 convertidos a nulo (H09)',
  duracion_dias int COMMENT 'Duración convertida a días (H18)',
  unspsc string COMMENT '8 dígitos sin el prefijo V1, nulo si es inválido (H10)',
  unspsc_segmento string,
  unspsc_familia string,
  unspsc_clase string,
  numero_lotes int,
  fecha_publicacion date COMMENT 'Hora de Colombia. Columna de partición',
  fecha_adjudicacion date,
  fecha_adjudicacion_es_respaldo boolean COMMENT 'true si se usó la fecha de publicación (H08)',
  estado string COMMENT 'abierto, adjudicado, cancelado o cerrado_sin_adjudicar (H17)',
  estado_origen string COMMENT 'estado_del_procedimiento original',
  adjudicado_origen string COMMENT 'Campo adjudicado original',
  apertura_origen string COMMENT 'estado_de_apertura_del_proceso original',
  ganador_codigo string COMMENT 'Código de proveedor SECOP del ganador (H06)',
  ganador_proveedor_key string COMMENT 'Hash SHA-256 del NIT del ganador',
  ganador_fuente string COMMENT 'codigo, nit o contrato. Nulo si no se identificó',
  valor_adjudicacion decimal(18, 2),
  respuestas_al_procedimiento int COMMENT 'Posterior al cierre: prohibida como feature (H20)',
  proveedores_unicos int COMMENT 'Posterior al cierre: prohibida como feature (H20)',
  visualizaciones int COMMENT 'Posterior al cierre: prohibida como feature (H20)',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Última modificación en Socrata. Nulo en el histórico',
  fecha_carga timestamp COMMENT 'Momento en que el job escribió la fila',
  url_proceso string COMMENT 'Enlace al proceso en SECOP II',
  fecha_limite_ofertas date COMMENT 'Fecha limite para recibir ofertas',
  dias_para_ofertar int COMMENT 'Dias entre publicacion y fecha limite de ofertas',
  precio_atipico boolean COMMENT 'precio_base mayor a 100 mil millones. No se borra',
  valor_atipico boolean COMMENT 'valor_adjudicacion mayor a 1.1 veces precio_base. Solo analitica',
  sector_entidad string COMMENT 'Sector mas frecuente de la entidad en contratos',
  n_proponentes int COMMENT 'Participaciones del proceso. Se conoce al cierre: no es feature del proceso',
  n_ganadores int COMMENT 'Proponentes con es_ganador true. Solo adjudicados')
PARTITIONED BY (year(`fecha_publicacion`))
LOCATION 's3://proyecto-integrador-bucket-01/silver/procesos'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);

CREATE TABLE secop_silver.procesos_rechazados (
  id_proceso string COMMENT 'Llave del proceso. Puede ser nula si la llave faltaba',
  regla string COMMENT 'R1, R2, R3 o R4',
  motivo string COMMENT 'fecha_publicacion_invalida, no_publicado, fuera_de_alcance o version_anterior',
  detalle string COMMENT 'Valor que causó el rechazo, por ejemplo la modalidad o la fecha recibida',
  registro_original string COMMENT 'Fila de bronce completa en JSON. Nula en fuera_de_alcance',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Última modificación en Socrata. Nulo en el histórico',
  id_corrida string COMMENT 'Ejecución del job que rechazó la fila. Ver secop_control.control_corridas',
  fecha_carga timestamp COMMENT 'Momento en que el job escribió la fila')
PARTITIONED BY (`motivo`)
LOCATION 's3://proyecto-integrador-bucket-01/silver/procesos_rechazados'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);

CREATE TABLE secop_silver.proponentes (
  id_proceso string COMMENT 'Llave del proceso CO1.REQ. Cruce con procesos.id_proceso',
  proveedor_key string COMMENT 'Hash SHA-256 del NIT normalizado. Identidad del proveedor (H05, H13)',
  codigo_proveedor string COMMENT 'Código de proveedor SECOP, solo dígitos. Llave para encontrar al ganador (H06)',
  es_persona_juridica boolean COMMENT 'true si el NIT corresponde a una empresa',
  nombre_proveedor string COMMENT 'Solo para personas jurídicas. Nulo para personas naturales',
  nit_entidad string COMMENT 'NIT normalizado de la entidad compradora',
  fecha_publicacion date COMMENT 'Hora de Colombia. Columna de partición',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Última modificación en Socrata. Nulo en el histórico',
  fecha_carga timestamp COMMENT 'Momento en que el job escribió la fila',
  es_ganador boolean COMMENT 'Ganador principal o firmante de un contrato del mismo portafolio. Nulo si no adjudicado',
  tipo_proveedor string COMMENT 'Del registro de proveedores, o provisional, o no_registrado')
PARTITIONED BY (year(`fecha_publicacion`))
LOCATION 's3://proyecto-integrador-bucket-01/silver/proponentes'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);

CREATE TABLE secop_silver.proponentes_rechazados (
  id_proceso string COMMENT 'Llave del proceso. Puede ser nula si faltaba',
  codigo_proveedor string COMMENT 'Código de proveedor SECOP. Puede ser nulo si faltaba',
  regla string COMMENT 'R1, R2 o R3',
  motivo string COMMENT 'llave_incompleta, proceso_inexistente, proceso_fuera_de_alcance o duplicado',
  detalle string COMMENT 'Valor que causó el rechazo',
  registro_original string COMMENT 'Fila de bronce en JSON con el documento del proveedor reemplazado por su hash. Nula en proceso_fuera_de_alcance',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Última modificación en Socrata. Nulo en el histórico',
  id_corrida string COMMENT 'Ejecución del job que rechazó la fila',
  fecha_carga timestamp COMMENT 'Momento en que el job escribió la fila')
PARTITIONED BY (`motivo`)
LOCATION 's3://proyecto-integrador-bucket-01/silver/proponentes_rechazados'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);

CREATE TABLE secop_silver.proveedores (
  proveedor_key string COMMENT 'Llave del proveedor, la misma de proponentes y contratos',
  codigo_proveedor string COMMENT 'Codigo SECOP de la cuenta que representa al proveedor',
  tipo_proveedor string COMMENT 'empresa, consorcio, entidad_publica o persona_natural',
  es_persona_juridica boolean COMMENT 'Igual que en proponentes',
  nombre_proveedor string COMMENT 'Solo personas juridicas',
  es_pyme boolean COMMENT 'Del registro. Una sola version',
  tipo_empresa string COMMENT 'Valor original del registro',
  departamento string COMMENT 'Departamento declarado',
  municipio string COMMENT 'Municipio declarado',
  unspsc_familia_declarada string COMMENT 'Familia UNSPSC de 4 digitos de la categoria principal',
  fecha_registro date COMMENT 'Creacion de la cuenta mas antigua del proveedor',
  esta_activa boolean COMMENT 'Cuenta activa en SECOP',
  es_usuario_objetivo boolean COMMENT 'Empresa o persona natural con cuenta activa',
  cuentas_secop int COMMENT 'Cuentas de SECOP consolidadas en esta llave',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Ultima modificacion en Socrata',
  fecha_carga timestamp COMMENT 'Momento en que el job escribio la fila')
LOCATION 's3://proyecto-integrador-bucket-01/silver/proveedores'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='zstd'
);

CREATE TABLE secop_silver.proveedores_rechazados (
  codigo_proveedor string COMMENT 'Codigo SECOP',
  proveedor_key string COMMENT 'Llave calculada, si la hubo',
  regla string COMMENT 'R1, R2 o R3',
  motivo string COMMENT 'llave_incompleta, version_anterior o cuenta_consolidada',
  detalle string COMMENT 'Explicacion del rechazo',
  registro_original string COMMENT 'Fila de bronce en JSON: solo columnas permitidas y NIT con hash',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Ultima modificacion en Socrata',
  id_corrida string COMMENT 'Corrida que lo rechazo',
  fecha_carga timestamp COMMENT 'Momento en que el job escribio la fila')
LOCATION 's3://proyecto-integrador-bucket-01/silver/proveedores_rechazados'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='zstd'
);

CREATE TABLE secop_silver.contratos (
  id_contrato string COMMENT 'Llave del contrato CO1.PCCNTR. Llave del MERGE',
  id_portafolio string COMMENT 'CO1.BDOS. Cruce con procesos.id_portafolio (H04)',
  con_proceso boolean COMMENT 'true si el portafolio existe en secop_silver.procesos (H04b)',
  nit_entidad string COMMENT 'NIT normalizado de la entidad compradora',
  nombre_entidad string,
  departamento string,
  ciudad string,
  sector string,
  orden string,
  proveedor_key string COMMENT 'Hash SHA-256 del documento normalizado del proveedor (H13)',
  codigo_proveedor string COMMENT 'Código de proveedor SECOP, solo dígitos',
  tipo_documento_proveedor string COMMENT 'NIT, cédula de ciudadanía, cédula de extranjería, etc.',
  es_persona_juridica boolean COMMENT 'true si el proveedor es una empresa',
  nombre_proveedor string COMMENT 'Solo para personas jurídicas. Nulo para personas naturales',
  es_pyme boolean COMMENT 'Valor declarado en el contrato',
  modalidad string COMMENT 'Modalidad del contrato. Puede estar fuera del alcance de procesos',
  tipo_contrato string,
  estado_contrato string,
  unspsc string COMMENT '8 dígitos sin el prefijo V1, nulo si es inválido (H10)',
  unspsc_segmento string,
  unspsc_familia string,
  unspsc_clase string,
  valor_contrato decimal(18, 2) COMMENT 'Valores menores o iguales a 0 convertidos a nulo (H09)',
  fecha_firma timestamp COMMENT 'Hora de Colombia. Columna de partición',
  fecha_inicio date,
  fecha_fin date,
  duracion_dias int COMMENT 'Duración convertida a días (H18)',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Última modificación en Socrata. Nulo en el histórico',
  fecha_carga timestamp COMMENT 'Momento en que el job escribió la fila',
  es_cedido boolean COMMENT 'Contrato cedido: no cuenta como experiencia de quien lo firmo',
  tipo_proveedor string COMMENT 'Del registro de proveedores, o provisional, o no_registrado')
PARTITIONED BY (year(`fecha_firma`))
LOCATION 's3://proyecto-integrador-bucket-01/silver/contratos'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);

CREATE TABLE secop_silver.contratos_rechazados (
  id_contrato string COMMENT 'Llave del contrato. Puede ser nula si faltaba',
  id_portafolio string COMMENT 'Proceso de compra. Puede ser nulo si faltaba',
  regla string COMMENT 'R1 o R2',
  motivo string COMMENT 'llave_incompleta o version_anterior',
  detalle string COMMENT 'Valor que causó el rechazo',
  registro_original string COMMENT 'Fila de bronce en JSON sin datos personales y con el documento del proveedor reemplazado por su hash',
  fuente string COMMENT 'historico o ingesta',
  sys_updated_at timestamp COMMENT 'Última modificación en Socrata. Nulo en el histórico',
  id_corrida string COMMENT 'Ejecución del job que rechazó la fila',
  fecha_carga timestamp COMMENT 'Momento en que el job escribió la fila')
PARTITIONED BY (`motivo`)
LOCATION 's3://proyecto-integrador-bucket-01/silver/contratos_rechazados'
TBLPROPERTIES (
  'table_type'='iceberg',
  'write_compression'='snappy',
  'format'='parquet'
);
