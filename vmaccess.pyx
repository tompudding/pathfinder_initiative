from libc.stdint cimport uint8_t, uintptr_t
from libc.stdlib cimport malloc, free
from libc.errno cimport errno
from libc.string cimport strerror
cdef extern from "sys/uio.h":
    struct iovec:
        void *iov_base
        size_t iov_len
    ssize_t process_vm_readv(int pid, iovec *local_iov,
                             unsigned long liovcnt,
                             iovec *remote_iov,
                             unsigned long riovcnt,
                             unsigned long flags)


def vm_read(int pid, uintptr_t addr, int len):
    cdef uint8_t *mem = <uint8_t*>malloc(len)
    cdef uintptr_t mem_int = <uintptr_t>mem
    cdef iovec local
    cdef iovec remote
    
    if mem == NULL:
        raise MemoryError()

    try:
        local.iov_base = mem
        local.iov_len = len
        remote.iov_base = <void*>addr
        remote.iov_len = len
        result = process_vm_readv(pid, &local, 1, &remote, 1, 0);
        if len != result:
            raise RuntimeError(strerror(errno))
        return mem[:len]
    finally:
        free(mem)
