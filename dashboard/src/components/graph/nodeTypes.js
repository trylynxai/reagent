import LLMNode from './LLMNode.jsx';
import ToolNode from './ToolNode.jsx';
import RetrievalNode from './RetrievalNode.jsx';
import ErrorNode from './ErrorNode.jsx';

const nodeTypes = {
  llmNode: LLMNode,
  toolNode: ToolNode,
  retrievalNode: RetrievalNode,
  errorNode: ErrorNode,
};

export default nodeTypes;
