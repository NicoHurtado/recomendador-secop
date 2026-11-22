-- Capa bronce · tablas de la ingesta incremental (NDJSON en gzip, partición fecha=AAAA-MM-DD por proyección)
-- Las tablas *_hist (carga histórica) las crea el job secop-bronze-historico-parquet.

CREATE EXTERNAL TABLE `secop_bronze.raw_procesos`(
  `entidad` string,
  `nit_entidad` string,
  `departamento_entidad` string,
  `ciudad_entidad` string,
  `ordenentidad` string,
  `codigo_pci` string,
  `id_del_proceso` string,
  `referencia_del_proceso` string,
  `ppi` string,
  `id_del_portafolio` string,
  `nombre_del_procedimiento` string,
  `descripci_n_del_procedimiento` string,
  `fase` string,
  `fecha_de_publicacion_del` string,
  `fecha_de_ultima_publicaci` string,
  `fecha_de_publicacion_fase` string,
  `fecha_de_publicacion_fase_1` string,
  `fecha_de_publicacion` string,
  `fecha_de_publicacion_fase_2` string,
  `fecha_de_publicacion_fase_3` string,
  `precio_base` string,
  `modalidad_de_contratacion` string,
  `justificaci_n_modalidad_de` string,
  `duracion` string,
  `unidad_de_duracion` string,
  `fecha_de_recepcion_de` string,
  `fecha_de_apertura_de_respuesta` string,
  `fecha_de_apertura_efectiva` string,
  `ciudad_de_la_unidad_de` string,
  `nombre_de_la_unidad_de` string,
  `proveedores_invitados` string,
  `proveedores_con_invitacion` string,
  `visualizaciones_del` string,
  `proveedores_que_manifestaron` string,
  `respuestas_al_procedimiento` string,
  `respuestas_externas` string,
  `conteo_de_respuestas_a_ofertas` string,
  `proveedores_unicos_con` string,
  `numero_de_lotes` string,
  `estado_del_procedimiento` string,
  `id_estado_del_procedimiento` string,
  `adjudicado` string,
  `id_adjudicacion` string,
  `codigoproveedor` string,
  `departamento_proveedor` string,
  `ciudad_proveedor` string,
  `fecha_adjudicacion` string,
  `valor_total_adjudicacion` string,
  `nombre_del_adjudicador` string,
  `nombre_del_proveedor` string,
  `nit_del_proveedor_adjudicado` string,
  `codigo_principal_de_categoria` string,
  `estado_de_apertura_del_proceso` string,
  `tipo_de_contrato` string,
  `subtipo_de_contrato` string,
  `categorias_adicionales` string,
  `urlproceso` string,
  `codigo_entidad` string,
  `estado_resumen` string,
  `sys_id` string,
  `sys_created_at` string,
  `sys_updated_at` string)
PARTITIONED BY (
  `fecha` string)
ROW FORMAT SERDE
  'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
  'ignore.malformed.json'='true',
  'mapping.sys_created_at'=':created_at',
  'mapping.sys_id'=':id',
  'mapping.sys_updated_at'=':updated_at')
STORED AS INPUTFORMAT
  'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT
  'org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat'
LOCATION
  's3://proyecto-integrador-bucket-01/bronze/procesos-contratacion/ingesta'
TBLPROPERTIES (
  'projection.enabled'='true',
  'projection.fecha.format'='yyyy-MM-dd',
  'projection.fecha.interval'='1',
  'projection.fecha.interval.unit'='DAYS',
  'projection.fecha.range'='2026-10-29,NOW',
  'projection.fecha.type'='date',
  'storage.location.template'='s3://proyecto-integrador-bucket-01/bronze/procesos-contratacion/ingesta/fecha=${fecha}/');

CREATE EXTERNAL TABLE `secop_bronze.raw_proponentes`(
  `id_procedimiento` string,
  `fecha_publicaci_n` string,
  `nombre_procedimiento` string,
  `nit_entidad` string,
  `codigo_entidad` string,
  `entidad_compradora` string,
  `proveedor` string,
  `nit_proveedor` string,
  `codigo_proveedor` string,
  `sys_id` string,
  `sys_created_at` string,
  `sys_updated_at` string)
PARTITIONED BY (
  `fecha` string)
ROW FORMAT SERDE
  'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
  'ignore.malformed.json'='true',
  'mapping.sys_created_at'=':created_at',
  'mapping.sys_id'=':id',
  'mapping.sys_updated_at'=':updated_at')
STORED AS INPUTFORMAT
  'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT
  'org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat'
LOCATION
  's3://proyecto-integrador-bucket-01/bronze/proponentes-procesos/ingesta'
TBLPROPERTIES (
  'projection.enabled'='true',
  'projection.fecha.format'='yyyy-MM-dd',
  'projection.fecha.interval'='1',
  'projection.fecha.interval.unit'='DAYS',
  'projection.fecha.range'='2026-10-27,NOW',
  'projection.fecha.type'='date',
  'storage.location.template'='s3://proyecto-integrador-bucket-01/bronze/proponentes-procesos/ingesta/fecha=${fecha}/');

CREATE EXTERNAL TABLE `secop_bronze.raw_contratos`(
  `nombre_entidad` string,
  `nit_entidad` string,
  `departamento` string,
  `ciudad` string,
  `localizaci_n` string,
  `orden` string,
  `sector` string,
  `rama` string,
  `entidad_centralizada` string,
  `proceso_de_compra` string,
  `id_contrato` string,
  `referencia_del_contrato` string,
  `estado_contrato` string,
  `codigo_de_categoria_principal` string,
  `descripcion_del_proceso` string,
  `tipo_de_contrato` string,
  `modalidad_de_contratacion` string,
  `justificacion_modalidad_de` string,
  `fecha_de_firma` string,
  `fecha_de_inicio_del_contrato` string,
  `fecha_de_fin_del_contrato` string,
  `condiciones_de_entrega` string,
  `tipodocproveedor` string,
  `documento_proveedor` string,
  `proveedor_adjudicado` string,
  `es_grupo` string,
  `es_pyme` string,
  `habilita_pago_adelantado` string,
  `liquidaci_n` string,
  `obligaci_n_ambiental` string,
  `obligaciones_postconsumo` string,
  `reversion` string,
  `origen_de_los_recursos` string,
  `destino_gasto` string,
  `valor_del_contrato` string,
  `valor_de_pago_adelantado` string,
  `valor_facturado` string,
  `valor_pendiente_de_pago` string,
  `valor_pagado` string,
  `valor_amortizado` string,
  `valor_pendiente_de` string,
  `valor_pendiente_de_ejecucion` string,
  `saldo_cdp` string,
  `saldo_vigencia` string,
  `espostconflicto` string,
  `dias_adicionados` string,
  `puntos_del_acuerdo` string,
  `pilares_del_acuerdo` string,
  `urlproceso` string,
  `nombre_representante_legal` string,
  `nacionalidad_representante_legal` string,
  `domicilio_representante_legal` string,
  `tipo_de_identificaci_n_representante_legal` string,
  `identificaci_n_representante_legal` string,
  `g_nero_representante_legal` string,
  `presupuesto_general_de_la_nacion_pgn` string,
  `sistema_general_de_participaciones` string,
  `sistema_general_de_regal_as` string,
  `recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_` string,
  `recursos_de_credito` string,
  `recursos_propios` string,
  `ultima_actualizacion` string,
  `codigo_entidad` string,
  `codigo_proveedor` string,
  `fecha_inicio_liquidacion` string,
  `fecha_fin_liquidacion` string,
  `objeto_del_contrato` string,
  `duraci_n_del_contrato` string,
  `nombre_del_banco` string,
  `tipo_de_cuenta` string,
  `n_mero_de_cuenta` string,
  `el_contrato_puede_ser_prorrogado` string,
  `fecha_de_notificaci_n_de_prorrogaci_n` string,
  `nombre_ordenador_del_gasto` string,
  `tipo_de_documento_ordenador_del_gasto` string,
  `n_mero_de_documento_ordenador_del_gasto` string,
  `nombre_supervisor` string,
  `tipo_de_documento_supervisor` string,
  `n_mero_de_documento_supervisor` string,
  `nombre_ordenador_de_pago` string,
  `tipo_de_documento_ordenador_de_pago` string,
  `n_mero_de_documento_ordenador_de_pago` string,
  `documentos_tipo` string,
  `descripcion_documentos_tipo` string,
  `direcci_n_de_ejecuci_n_del_contrato` string,
  `criterios_de_sostenibilidad_ambiental` string,
  `requisitos_ambientales_en_las_especificaciones_t_cnicas` string,
  `criterios_ambientales_en_la_evaluaci_n_de_las_ofertas` string,
  `obligaciones_contractuales_o_poscontractuales_a_nivel_ambiental` string,
  `uso_de_etiquetado_ecol_gico` string,
  `obligaciones_posconsumo` string,
  `fecha_inicio_obligaciones_posconsumo` string,
  `fecha_fin_obligaciones_posconsumo` string,
  `fecha_inicio_reversi_n` string,
  `fecha_fin_reversi_n` string,
  `sys_id` string,
  `sys_created_at` string,
  `sys_updated_at` string)
PARTITIONED BY (
  `fecha` string)
ROW FORMAT SERDE
  'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
  'ignore.malformed.json'='true',
  'mapping.sys_created_at'=':created_at',
  'mapping.sys_id'=':id',
  'mapping.sys_updated_at'=':updated_at')
STORED AS INPUTFORMAT
  'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT
  'org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat'
LOCATION
  's3://proyecto-integrador-bucket-01/bronze/contratos-electronicos/ingesta'
TBLPROPERTIES (
  'projection.enabled'='true',
  'projection.fecha.format'='yyyy-MM-dd',
  'projection.fecha.interval'='1',
  'projection.fecha.interval.unit'='DAYS',
  'projection.fecha.range'='2026-10-27,NOW',
  'projection.fecha.type'='date',
  'storage.location.template'='s3://proyecto-integrador-bucket-01/bronze/contratos-electronicos/ingesta/fecha=${fecha}/');
