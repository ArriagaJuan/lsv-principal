"""Compatibilidad de módulo con exportacion.py visto en video.

Delegamos en export_records, único productor Excel del monitor reconstruido.
"""
from exporter import export_records, prepare_export_directory, new_export_path

exportar_excel = export_records
__all__ = ['exportar_excel','export_records','prepare_export_directory','new_export_path']
