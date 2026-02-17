import { useQuery } from '@tanstack/react-query';
import { getDocuments, getDocumentStatus } from '@/api/documents';

export const documentKeys = {
  all: ['documents'] as const,
  status: (docId: string) => ['documents', 'status', docId] as const,
};

export function useDocuments() {
  return useQuery({
    queryKey: documentKeys.all,
    queryFn: getDocuments,
  });
}

export function useDocumentStatus(docId: string) {
  return useQuery({
    queryKey: documentKeys.status(docId),
    queryFn: () => getDocumentStatus(docId),
    enabled: !!docId,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.processing_status === 'processing' ? 5000 : false;
    },
  });
}
