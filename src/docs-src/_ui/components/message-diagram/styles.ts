/** Local presentation only; existing page roles and native text remain canonical. */
export const messageDiagramStyles = `
  display:block; min-width:0; max-width:100%;
  & > figure { margin:1.5rem 0; min-width:0; max-width:100%; }
  & > figure > figcaption { font-weight:600; margin-bottom:.75rem; }
  & .message-diagram-visual { width:100%; max-width:100%; overflow:hidden; margin-block:.75rem; background:var(--surface); border-radius:.5rem; }
  & .message-diagram-visual .joint-paper { position:relative; overflow:hidden; }
  & .message-diagram-visual svg { display:block; max-width:100%; overflow:hidden; }
  & .message-diagram-visual .joint-cell { cursor:default; pointer-events:none; }
  & .message-diagram-visual text { font-family:inherit; }
  & > figure > ol { padding-inline-start:1.5rem; }
`;
